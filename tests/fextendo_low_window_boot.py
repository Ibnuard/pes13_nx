"""Validate exact boot sources/artifacts and execute the descriptor reader tests.

Does not boot Horizon. Hardware A/B probes are a separate acceptance gate.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fextendo_low_window import AMS_REV, HOC_REV, SOURCE


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'dist/fextendo-low-window-v1')
    p.add_argument('--hoc', type=Path, default=Path('/mnt/d/Dev/Personal/UNDANGAN/hoc.kip'))
    a = p.parse_args()
    boot = a.output / 'boot'
    build = json.loads((boot / 'build.json').read_text())
    assert build['ams_revision'] == AMS_REV and build['hoc_revision'] == HOC_REV
    assert build['title_id_allowlist'] is None
    for name, digest in build['files'].items(): assert sha(boot / name) == digest, name
    for name, digest in build['prepared']['inputs'].items(): assert sha(ROOT / name) == digest, name
    for tree, files in build['prepared']['changes'].items():
        folder = a.work / tree
        for name, digest in files.items(): assert sha(folder / name) == digest, name
        subprocess.run(['git', '-C', str(folder), 'apply', '--reverse', '--check',
                        str(boot / (tree + '-fextendo.patch'))], check=True)
        abi = folder / 'libraries/libvapours/include/vapours/svc/svc_fextendo_memory.hpp'
        reader = folder / 'stratosphere/loader/source/ldr_fextendo_memory.inc'
        assert abi.read_bytes() == (SOURCE / 'fextendo_memory_abi.hpp').read_bytes()
        assert reader.read_bytes() == (SOURCE / 'ldr_fextendo_memory.inc').read_bytes()
        loader = (folder / 'stratosphere/loader/source/ldr_process_creation.cpp').read_text()
        assert 'HasAutorunLowWindow' not in loader and 'AutorunNativeAddressStart' not in loader
        assert loader.index('R_TRY(ApplyFextendoMemoryDescriptor(std::addressof(param)))') < loader.index(
            'R_TRY(DecideAddressSpaceLayout(out, std::addressof(param)') < loader.index('R_TRY(svc::CreateProcess(')
        block = loader.split('aslr_size  = svc::AddressMap39Size;', 1)[1].split('break;', 1)[0]
        assert 'if (svc::fextendo::Requested(out_param->flags))' in block
        assert 'aslr_start = svc::fextendo::NativeStart;' in block
        kernel = (folder / 'libraries/libmesosphere/source/svc/kern_svc_process.cpp').read_text()
        assert kernel.index('svc::fextendo::CompatibleFlags(params.flags)') < kernel.index('KProcess::Create()')
        assert 'params.code_address >= ams::svc::fextendo::NativeStart' in kernel
        process = (folder / 'libraries/libmesosphere/source/kern_k_process.cpp').read_text()
        assert 'ams::svc::fextendo::Requested(params.flags)' in process and 'HasAutorunLowWindow' not in process
        page = (folder / 'libraries/libmesosphere/source/kern_k_page_table_base.cpp').read_text()
        assert page.index('if (m_address_space_width == 39)') < page.index('if (low_window)')
        assert 'm_alias_code_region_start = ams::svc::AddressSmallMap32Start;' in page
        for content in (abi.read_text(), reader.read_text()):
            assert 'program_id' not in content and 'title_id' not in content
    user = a.hoc.read_bytes()
    assert sha(a.hoc) == build['hoc_input_sha256']
    kip = (boot / 'loader-hoc.kip').read_bytes()
    off, old, size = (build[n] for n in ('hoc_settings_output_offset', 'hoc_settings_original_offset', 'hoc_settings_bytes'))
    assert kip[off:off + size] == user[old:old + size]
    assert hashlib.sha256(kip[off:off + size]).hexdigest() == build['hoc_settings_sha256']
    for name in ('loader-hoc.kip', 'loader-stock.kip'):
        assert (boot / name).read_bytes()[:4] == b'KIP1'
    executable = a.work / 'descriptor-tests-final'
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g',
                    str(ROOT / 'tests/fextendo_low_window.cpp'), '-o', str(executable)], check=True)
    result = subprocess.check_output([str(executable)], text=True).strip()
    assert result.startswith('PASS 65836 ')
    probe = json.loads((a.output / 'probe-build.json').read_text())
    arm = json.loads((a.output / 'forwarder-tests.json').read_text())
    assert arm['status'] == 'PASS' and arm['forwarder_elf_sha256'] == probe['forwarder_elf_sha256']
    for name, digest in probe['source_files'].items(): assert sha(ROOT / name) == digest, name
    spec = importlib.util.spec_from_file_location('nsp_checks', ROOT / 'tools/build-fextendo-forwarder.py')
    nsp_checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nsp_checks)
    for fw in probe['forwarders']:
        nsp = a.output / 'forwarders' / fw['nsp']
        assert sha(nsp) == fw['sha256']
        npdms = []
        for nca in nsp_checks.pfs_files(nsp.read_bytes()).values():
            at = 0
            while True:
                at = nca.find(b'PFS0', at)
                if at < 0: break
                try:
                    files = nsp_checks.pfs_files(nca[at:])
                    if 'main.npdm' in files: npdms.append(files['main.npdm'])
                except (AssertionError, ValueError, struct.error, UnicodeError): pass
                at += 4
        assert len(npdms) == 1
        npdm = npdms[0]
        aci, acid = struct.unpack_from('<I4xI', npdm, 0x70)
        assert (npdm[12] & 15) == 7  # ARM64 / real 39-bit
        assert ((struct.unpack_from('<I', npdm, acid + 0x20c)[0] >> 2) & 15) == 0  # application pool
        for base, field in ((aci, 0x30), (acid, 0x230)):
            offset, size = struct.unpack_from('<II', npdm, base + field)
            caps = [item[0] for item in struct.iter_unpack('<I', npdm[base + offset:base + offset + size])]
            assert [c for c in caps if c & 0x3fff == 0x1fff] == [0x5fff]  # application type 1
    report = {'status': 'PASS', 'hardware_tested': False, 'descriptor_host_tests': result,
              'kernel_and_both_loaders_built': True, 'source_and_packaged_artifacts_verified': True,
              'hoc_settings_preserved': True, 'title_id_allowlist': None,
              'actual_arm64_forwarder_cases': arm['cases'], 'boot_files': build['files'],
              'tests': {name: sha(ROOT / name) for name in ('tests/fextendo_low_window.cpp',
                  'tests/fextendo_low_window_binary.py', 'tests/fextendo_low_window_boot.py')}}
    (a.output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS boot source integration, HOC settings, 65,836 fault/flag cases, artifact hashes and ARM64 forwarders')


if __name__ == '__main__': main()
