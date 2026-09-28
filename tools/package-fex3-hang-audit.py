"""Build a verified NRO-only update for an existing stability-540p installation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
NRO = 'switch/pes13-fex/pes13-fex.nro'


def load_helper(filename):
    spec = importlib.util.spec_from_file_location('helper', ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(candidate, baseline):
    checked = load_helper('package-fex3-stability.py').checked
    build = json.loads((candidate / 'runtime-build.json').read_text())
    old = json.loads((baseline / 'runtime-build.json').read_text())
    patches = json.loads((candidate / 'wine-patches.json').read_text())
    old_patches = json.loads((baseline / 'wine-patches.json').read_text())
    if any(build.get(k) is not True for k in ('integration',)):
        # Older build recipes encode integration through stability and the executable marker.
        if build.get('stability') is not True:
            raise ValueError('Requires stability integration')
    for key in ('hang_audit', 'resume_gate', 'runtime_fixes', 'samecore_yield', 'diagnostic'):
        if build.get(key) is not True:
            raise ValueError('Incorrect candidate flags: ' + key)
    for key in ('adapter_sources', 'native_dependencies', 'ntdll_sha256', 'wow64_sha256',
                'guest_sha256', 'toolchain_path'):
        if build[key] != old[key]:
            raise ValueError('NRO-only update cannot change matched dependency: ' + key)
    if patches['pe-source'] != old_patches['pe-source']:
        raise ValueError('PE source drift')
    delta = sorted(k for k in patches['native-source'].keys() | old_patches['native-source'].keys()
                   if patches['native-source'].get(k) != old_patches['native-source'].get(k))
    if delta != ['dlls/ntdll/unix/horizon.c', 'dlls/win32u/vulkan.c',
                 'wine-nx-probe/source/runtime.c', 'wine-nx-probe/source/thread_profile.c']:
        raise ValueError('Unexpected native delta: ' + repr(delta))
    for name, digest in build['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
    for name, digest in build['patch_sources'].items():
        checked(ROOT / name, digest)
    for directory, receipt in ((candidate, build), (baseline, old)):
        for name, key in (('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256'),
                          ('fex-stress.exe', 'guest_sha256')):
            checked(directory / 'payload' / name, receipt[key])
    blob = checked(candidate / 'payload/pes13-fex.nro', build['nro_sha256'])
    elf = candidate / 'reference/pes13-fex.elf'
    checked(elf, build['native_elf_sha256'])
    metadata = inspect_nro(blob, (ROOT / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13-NX FEX3', expected_version='0.3.0')
    load_helper('package-fex3-stability.py').verify_executable(elf, blob)
    if any(marker not in blob for marker in (b'pes13-fex3-hang-audit', b'[FEX3-SCALED]', b'[FEX3-HANG] v2')):
        raise ValueError('Missing candidate marker')
    if b'scaled present %d read back' in blob:
        raise ValueError('Diagnostic GPU readback remains linked')
    files = {NRO: blob, 'README.md': (ROOT / 'docs/FEX3-HANG-AUDIT.md').read_bytes(),
             'log-analysis.json': (candidate.parent / 'log-analysis.json').read_bytes()}
    for name in ('scaled', 'resume', 'sync', 'pipeline', 'samecore', 'dispatch', 'unwind'):
        path = candidate.parent / (name + '-binary.json')
        report = json.loads(path.read_text())
        if report.get('passed') is not True or report.get('native_elf_sha256') != build['native_elf_sha256']:
            raise ValueError('Invalid/stale linked test: ' + name)
        if name == 'unwind' and (report['ntdll_sha256'] != build['ntdll_sha256'] or
                                 report['wow64_sha256'] != build['wow64_sha256']):
            raise ValueError('Unwind PE dependency mismatch')
        files['evidence/' + path.name] = path.read_bytes()
    host = candidate.parent / 'host-validation.json'
    report = json.loads(host.read_text())
    if report.get('passed') is not True or report.get('lost_error_propagation_mutation_rejected') is not True:
        raise ValueError('Host validation failed')
    for name, digest in report['source_sha256'].items():
        if patches['native-source'].get(name) != digest:
            raise ValueError('Host tests do not match compiled source: ' + name)
    files['evidence/' + host.name] = host.read_bytes()
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/' + name] = (candidate / name).read_bytes()
    files['profiles/conservative-ordering.ini'] = (ROOT / 'config/fex/stability-540p.ini').read_bytes().replace(
        b'fex_fastest=1', b'fex_fastest=0')
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt'] = (ROOT / 'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (ROOT / 'src/fex/LICENSE').read_bytes()
    for path in (ROOT / 'licenses').rglob('*'):
        if path.is_file() and path.name != 'Box64-LICENSE.txt':
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    record = {'kind': 'Scaled-present fix and bounded hang diagnosis; NRO-only update',
              'hardware_tested': False, 'hang_fix_verified': False, 'replaces': [NRO],
              'requires_existing_package': 'pes13-fex3-stability-540p',
              'native_elf_sha256': build['native_elf_sha256'], 'metadata': metadata,
              'native_source_delta': delta, 'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(record, indent=2) + '\n').encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=ROOT / 'local/fex3/hang-audit/runtime')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'local/fex3/stability-540p/runtime')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-fex3-hang-audit.zip')
    args = parser.parse_args()
    folder = args.output.with_suffix('')
    if folder.exists() or args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing package')
    files = collect(args.candidate, args.baseline)
    result = load_helper('package-fex3-runtime-fixes.py').write_overlay(args.output, files)
    folder.mkdir()
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if path.read_bytes() != data:
            raise RuntimeError('Folder readback mismatch')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
