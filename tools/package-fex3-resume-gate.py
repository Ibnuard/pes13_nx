"""Package isolated resume-gate NRO after verifying ABI and linked-binary receipts."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NRO = 'switch/pes13-fex/pes13-fex.nro'
MARKER = b'[FEX3-RESUME] isolated self-suspend wake'
YIELD = b'[FEX3-YIELD] same-core Sleep(0) experiment'
SPEC = importlib.util.spec_from_file_location('event_package', ROOT / 'tools/package-fex3-event-diagnostic.py')
if SPEC is None or SPEC.loader is None:
    raise RuntimeError('Cannot load NRO verification helpers')
EVENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVENT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_executable(elf, blob):
    """Reproduce executable bytes from the tested ELF; metadata checked separately."""
    scratch = Path.home() / '.hermes/cache/scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fex-nro-check-', dir=scratch) as directory:
        repacked = Path(directory) / 'executable.nro'
        subprocess.run(['/opt/devkitpro/tools/bin/elf2nro', str(elf), str(repacked)],
                       check=True, capture_output=True, timeout=60)
        size = struct.unpack_from('<I', blob, 0x18)[0]
        if repacked.read_bytes() != blob[:size]:
            raise ValueError('NRO executable differs from validated ELF')


def package(control_dir, candidate_dir, destination):
    control_dir, candidate_dir = Path(control_dir), Path(candidate_dir)
    control, cp, old_blob, _ = EVENT.load(control_dir, 'pes13-fex3-event-diagnostic')
    candidate, dp, blob, metadata = EVENT.load(candidate_dir, 'pes13-fex3-event-diagnostic')
    verify_executable(candidate_dir / 'reference/pes13-fex.elf', blob)
    for receipt in (control, candidate):
        if receipt.get('runtime_fixes') is not False or receipt.get('diagnostic') is not True:
            raise ValueError('Requires diagnostic baseline without runtime-fixes')
    if candidate.get('resume_gate') is not True or candidate.get('samecore_yield') is not True:
        raise ValueError('Incorrect candidate experiment flags')
    if control.get('resume_gate', False) is not False or MARKER in old_blob or MARKER not in blob:
        raise ValueError('Incorrect resume-gate marker')
    if YIELD not in blob or YIELD not in old_blob:
        raise ValueError('Yield policy must match last hardware baseline')
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'adapter_sources',
                'toolchain_path', 'native_dependencies'):
        if key not in candidate or candidate[key] != control.get(key):
            raise ValueError('Control/candidate ABI drift: ' + key)
    for directory, receipt in ((control_dir, control), (candidate_dir, candidate)):
        for name, field in (('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256'),
                            ('fex-stress.exe', 'guest_sha256')):
            if sha((directory / 'payload' / name).read_bytes()) != receipt[field]:
                raise ValueError('PE payload drift: ' + name)
    if cp['pe-source'] != dp['pe-source']:
        raise ValueError('PE source drift')
    delta = sorted(name for name in cp['native-source'].keys() | dp['native-source'].keys()
                   if cp['native-source'].get(name) != dp['native-source'].get(name))
    if delta != ['dlls/ntdll/unix/horizon.c', 'wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source changes: ' + repr(delta))
    for path, digest in candidate['patch_sources'].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError('Changed patch source: ' + path)
    allowed = {'tools/build-fex-runtime.py', 'tools/fex_wine_patches.py',
               'tools/fex_resume_patches.py', 'src/runtime/fex_resume_runtime.h'}
    changed = {name for name in control['patch_sources'].keys() | candidate['patch_sources'].keys()
               if control['patch_sources'].get(name) != candidate['patch_sources'].get(name)}
    if changed - allowed:
        raise ValueError('Unrelated patch changes: ' + repr(sorted(changed - allowed)))
    for name, digest in candidate['adapter_sources'].items():
        if sha((ROOT / 'src/fex' / name).read_bytes()) != digest:
            raise ValueError('Changed adapter source: ' + name)
    validations = {}
    for filename in ('resume-validation.json', 'samecore-validation.json',
                     'sync-validation.json', 'pipeline-validation.json', 'unwind-validation.json'):
        data = (candidate_dir / filename).read_bytes()
        report = json.loads(data)
        if report.get('passed') is not True or report.get('native_elf_sha256') != candidate['native_elf_sha256']:
            raise ValueError('Invalid/stale linked validation: ' + filename)
        if filename == 'resume-validation.json' and report.get('scenarios') != 15:
            raise ValueError('Incomplete resume-gate validation')
        if filename == 'samecore-validation.json':
            expected = [('NtYieldExecution', None, [0]), ('NtDelayExecution', 0, [0]),
                        ('NtDelayExecution', -10000, [0, 1000000]),
                        ('NtDelayExecution', -50000, [0, 5000000]),
                        ('NtDelayExecution', 999999999, [0])]
            actual = [(c.get('function'), c.get('timeout_100ns'), c.get('svc_sleep_ns'))
                      for c in report.get('checks', [])]
            if report.get('expected_yield_ns') != 0 or actual != expected:
                raise ValueError('Contradictory yield/delay validation')
        validations[filename] = sha(data)
    record = {'kind': 'isolated self-suspend resume-gate candidate',
              'target': 'Nintendo Switch / Horizon ARM64', 'hardware_tested': False,
              'resume_gate': True, 'samecore_yield': True, 'runtime_fixes': False,
              'replaces': [NRO], 'control_nro_sha256': control['nro_sha256'],
              'nro_sha256': candidate['nro_sha256'], 'native_elf_sha256': candidate['native_elf_sha256'],
              'native_source_delta': delta, 'validation_sha256': validations, 'metadata': metadata}
    readme = (
        'PES13 FEX3 resume-gate candidate. Belum diuji di Switch.\n\n'
        '1. Tutup game lewat HOME lalu X. Backup NRO playable dan log.\n'
        '2. Ekstrak ke root SD. Hanya switch/pes13-fex/pes13-fex.nro diganti.\n'
        '3. Pertahankan DLL, settings.dat, dxvk.conf, save, cache, clock dan preset.\n'
        '4. Uji kickoff pertama, shoot/bola cepat, goal kick lawan dan rangkaian corner.\n'
        '5. Simpan log + video sebelum relaunch. Jika regresi, pulihkan NRO backup.\n\n'
        'Delta terhadap samecore: self-suspend menunggu condition pribadi; resume\n'
        'membangunkan object cocok saat suspend count mencapai nol. Broadcast\n'
        'event/semaphore tidak lagi membangunkan self-suspend yang tidak terkait.\n'
        'Start gate, termination, nested count dan 20ms safety recheck dipertahankan.\n'
        'Timer/QPC, cache path, affinity, shader settings tidak diubah.\n'
        'Same-core yield tetap hanya untuk menjaga satu variabel terhadap run terakhir.\n'
        'Bukan klaim ketiga gejala sudah hilang; manfaat gameplay perlu uji hardware.\n'
        'Marker: [FEX3-RESUME] isolated self-suspend wake\n'
    ).encode()
    files = {NRO: blob, 'README.txt': readme,
             'manifest.json': (json.dumps(record, indent=2) + '\n').encode()}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files) or any(
                archive.read(name) != data for name, data in files.items()):
            raise RuntimeError('Archive verification failed')
    record['archive_path'] = str(destination.resolve())
    record['archive_sha256'] = sha(destination.read_bytes())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, default=ROOT / 'local/fex3/samecore-diagnostic')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'local/fex3/resume-gate')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-fex3-resume-gate.zip')
    args = parser.parse_args()
    print(json.dumps(package(args.control, args.candidate, args.output), indent=2))


if __name__ == '__main__':
    main()
