"""Package isolated same-core-yield experiment; preserve tested diagnostic baseline."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NRO = 'switch/pes13-fex/pes13-fex.nro'
MARKER = b'[FEX3-YIELD] same-core Sleep(0) experiment'
SPEC = importlib.util.spec_from_file_location('event_package', ROOT / 'tools/package-fex3-event-diagnostic.py')
assert SPEC is not None and SPEC.loader is not None
EVENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVENT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(control_dir, candidate_dir, destination):
    control_dir, candidate_dir = Path(control_dir), Path(candidate_dir)
    control, cp, control_nro, _ = EVENT.load(control_dir, 'pes13-fex3-event-diagnostic')
    candidate, dp, blob, metadata = EVENT.load(candidate_dir, 'pes13-fex3-event-diagnostic')
    for receipt in (control, candidate):
        if receipt.get('runtime_fixes') is not False or receipt.get('diagnostic') is not True:
            raise ValueError('Both variants must be diagnostic control without runtime-fixes')
    if MARKER in control_nro or MARKER not in blob or b'[FEX3-EVENT]' not in blob:
        raise ValueError('Incorrect control/candidate yield or diagnostic marker')
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'adapter_sources',
                'toolchain_path', 'native_dependencies', 'patch_sources'):
        if key not in candidate or candidate[key] != control.get(key):
            raise ValueError('Control/candidate drift: ' + key)
    for directory, receipt in ((control_dir, control), (candidate_dir, candidate)):
        for filename, field in (('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256'),
                                ('fex-stress.exe', 'guest_sha256')):
            if sha((directory / 'payload' / filename).read_bytes()) != receipt[field]:
                raise ValueError('PE payload drift: ' + filename)
    if cp['pe-source'] != dp['pe-source']:
        raise ValueError('PE source drift')
    delta = sorted(name for name in cp['native-source'].keys() | dp['native-source'].keys()
                   if cp['native-source'].get(name) != dp['native-source'].get(name))
    if delta != ['dlls/ntdll/unix/sync.c', 'wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source changes: ' + repr(delta))
    for path, digest in candidate['patch_sources'].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError('Changed patch source: ' + path)
    for name, digest in candidate['adapter_sources'].items():
        if sha((ROOT / 'src/fex' / name).read_bytes()) != digest:
            raise ValueError('Changed adapter source: ' + name)
    validations = {}
    for filename, receipt, expected in (
            ('samecore-control-validation.json', control, -1),
            ('samecore-validation.json', candidate, 0),
            ('self-suspend-validation.json', candidate, None),
            ('sync-validation.json', candidate, None),
            ('pipeline-validation.json', candidate, None),
            ('unwind-validation.json', candidate, None)):
        data = (candidate_dir / filename).read_bytes()
        report = json.loads(data)
        if report.get('passed') is not True or report.get('native_elf_sha256') != receipt['native_elf_sha256']:
            raise ValueError('Invalid or stale binary validation: ' + filename)
        if expected is not None and (report.get('expected_yield_ns') != expected or len(report.get('checks', [])) != 5):
            raise ValueError('Wrong yield validation: ' + filename)
        validations[filename] = sha(data)
    record = {
        'kind': 'same-core yield experiment on event diagnostic',
        'target': 'Nintendo Switch / Horizon ARM64', 'hardware_tested': False,
        'samecore_yield': True, 'runtime_fixes': False, 'diagnostic': True,
        'replaces': [NRO], 'control_nro_sha256': control['nro_sha256'],
        'control_native_elf_sha256': control['native_elf_sha256'],
        'nro_sha256': candidate['nro_sha256'], 'native_elf_sha256': candidate['native_elf_sha256'],
        'native_source_delta': delta, 'validation_sha256': validations, 'metadata': metadata,
        'yield_scope': 'NtYieldExecution, including Sleep(0), SwitchToThread and initial yield before timed sleeps',
    }
    readme = (
        'PES13-NX FEX3 same-core yield experiment; belum diuji di Switch.\n\n'
        '1. Tutup game lewat HOME lalu X. Backup NRO aktif dan log sebelum mengganti.\n'
        '2. Ekstrak ke root SD. Hanya switch/pes13-fex/pes13-fex.nro diganti.\n'
        '3. Pertahankan DLL, settings.dat, dxvk.conf, save, cache, preset, tim, stadion, kamera, clock.\n'
        '4. Rekam kickoff pertama, permainan aktif, corner, goal kick, dan kickoff setelah gol.\n'
        '5. Simpan log + video kandidat sebelum membuka game lagi. Ulangi dengan NRO backup.\n'
        '6. Jika menu/kickoff makin berat atau macet, tutup game dan pulihkan NRO backup.\n\n'
        'Perubahan: NtYieldExecution memakai svcSleepThread(0), sebelumnya -1.\n'
        'Berlaku pada Sleep(0), SwitchToThread, dan yield awal sebelum timed sleep.\n'
        'Durasi timed sleep, timer, affinity, cache path, dan konfigurasi tidak diubah.\n'
        'Marker log: [FEX3-YIELD] same-core Sleep(0) experiment\n'
        'Probe [FEX3-EVENT], [FEX3-PACE], [FEX3-DELAY] tetap.\n'
        'Target: mengurangi contention; bukan klaim fix kickoff, stutter, atau slow-mo.\n'
        'Present bukan frame layar unik; video jam dan gerak 3D tetap diperlukan.\n'
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
    record['archive_sha256'] = sha(destination.read_bytes())
    record['archive_path'] = str(destination.resolve())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, default=ROOT / 'local/fex3/event-diagnostic')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'local/fex3/samecore-diagnostic')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-fex3-samecore-diagnostic.zip')
    args = parser.parse_args()
    print(json.dumps(package(args.control, args.candidate, args.output), indent=2))


if __name__ == '__main__':
    main()
