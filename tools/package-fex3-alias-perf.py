"""Package paired FEX performance candidates and an exact runtime rollback."""
from pathlib import Path
import hashlib
import json
import zipfile

import pefile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/alias-perf'
BASE = ROOT / 'local/fex3/compact-callret/module/libwow64fex.dll'
NEW = WORK / 'module/libwow64fex.dll'
DLL_PATH = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
NRO_PATH = 'switch/pes13-fex/pes13-fex.nro'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def interface(data):
    pe = pefile.PE(data=data)
    try:
        exports = {(s.name, s.ordinal, s.forwarder) for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        imports = {(directory, dep.dll, tuple((e.name, e.ordinal) for e in dep.imports))
                   for directory in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                   for dep in getattr(pe, directory, [])}
        return pe.FILE_HEADER.Machine, exports, imports
    finally:
        pe.close()


def verified_build(path, report, field):
    data = path.read_bytes()
    assert digest(data) == json.loads(report.read_text())[field], path
    return data


def archive(name, files):
    target = ROOT / 'dist' / name
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as output:
        for path, data in sorted(files.items()):
            entry = zipfile.ZipInfo(path, (2026, 9, 25, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(entry, data)
    with zipfile.ZipFile(target) as check:
        assert check.testzip() is None
        assert set(check.namelist()) == set(files)
        for path, data in files.items():
            assert check.read(path) == data
        assert {p for p in check.namelist() if p.startswith('switch/')} == {DLL_PATH, NRO_PATH}
    return {'path': str(target), 'sha256': digest(target.read_bytes()), 'bytes': target.stat().st_size}


def main():
    old_dll = BASE.read_bytes()
    new_dll = verified_build(NEW, WORK / 'module/build.json', 'sha256')
    assert digest(old_dll) == '235cbce7a7221876152374cf2533ebe8dd11a08d933e3493d57c04d6e66ad3bc'
    assert interface(old_dll) == interface(new_dll), 'PE import/export ABI changed'
    assert interface(new_dll)[0] == 0xaa64
    old_nro = verified_build(WORK / 'before/pes13-fex.nro',
                             WORK / 'before/runtime-build.json', 'nro_sha256')
    control_nro = verified_build(WORK / 'diagnostic/pes13-fex.nro',
                                 WORK / 'diagnostic/runtime-build.json', 'nro_sha256')
    samecore_nro = verified_build(WORK / 'samecore/pes13-fex.nro',
                                  WORK / 'samecore/runtime-build.json', 'nro_sha256')
    assert len({digest(old_nro), digest(control_nro), digest(samecore_nro)}) == 3
    tests = {name: json.loads((WORK / f'{name}-tests.json').read_text())
             for name in ('alias', 'abi', 'alloc', 'memory', 'code-growth')}
    assert all(row['passed'] and row['dll_sha256'] == digest(new_dll)
               for row in tests.values())
    assert tests['alias']['cache_writes_without_native_lookup'] >= 100
    assert tests['alias']['native_alias_callbacks'] == 4
    common = {
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'FEX3-PERF-EXPERIMENT.md': (ROOT / 'docs/FEX3-PERF-EXPERIMENT.md').read_bytes(),
        'licenses/FEX/LICENSE': (WORK / 'module/licenses/LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
    }
    for name, row in tests.items():
        common[f'validation/{name}-tests.json'] = (WORK / f'{name}-tests.json').read_bytes()
    manifest = {
        'source_log_sha256': digest((WORK / 'before/fex-runtime.log').read_bytes()),
        'fex_commit': json.loads((WORK / 'module/build.json').read_text())['fex_commit'],
        'previous_dll_sha256': digest(old_dll),
        'candidate_dll_sha256': digest(new_dll),
        'previous_nro_sha256': digest(old_nro),
        'control_nro_sha256': digest(control_nro),
        'samecore_nro_sha256': digest(samecore_nro),
        'hardware_performance_verified': False,
        'candidate_changes': {
            'both': ['PE-local JIT RW alias lookup', 'bounded HMAP failure diagnostics'],
            'samecore_only': ['Sleep(0) yields on the current core instead of requesting migration'],
        },
    }
    common['FEX3-alias-perf-manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    results = {}
    for label, nro in (('control', control_nro), ('samecore', samecore_nro)):
        readme = (
            'PES13-NX FEX3 JIT alias performance experiment: ' + label + '\n\n'
            'Tutup aplikasi lewat HOME -> X. Ekstrak ZIP ini ke root microSD; '
            'timpa dua file pada switch/pes13-fex. Jangan campur dua varian.\n'
            'Game, konfigurasi, prefix, dan save tidak disertakan/diganti. '
            'Pastikan run_guest_tests=0 untuk PES.\n\n'
            'Control mempertahankan perilaku scheduler lama. Samecore hanya '
            'mengubah yield Sleep(0) di atas perubahan control. Keduanya '
            'mencatat [FEX3-HMAP] jika commit gagal.\n'
            'Bandingkan dengan OC dan urutan menu yang sama: waktu ke menu, '
            'kelancaran 2D, team selection, audio, dan match bila tercapai. '
            'Simpan fex-runtime.log sebelum launch ulang. Performa Switch '
            'belum diverifikasi; 30 FPS belum diklaim.\n'
        ).encode()
        files = dict(common, **{DLL_PATH: new_dll, NRO_PATH: nro, 'README.txt': readme})
        results[label] = archive(f'pes13-fex3-alias-perf-{label}.zip', files)
    rollback = dict(common, **{
        DLL_PATH: old_dll,
        NRO_PATH: old_nro,
        'README.txt': (
            'PES13-NX FEX3 rollback\n\nTutup lewat HOME -> X, lalu ekstrak '
            'ke root microSD. Mengembalikan NRO dan DLL compact-callret '
            'persis seperti sebelum dua varian eksperimen ini.\n'
        ).encode(),
    })
    results['rollback'] = archive('pes13-fex3-alias-perf-rollback.zip', rollback)
    (WORK / 'package.json').write_text(json.dumps({'manifest': manifest, 'archives': results}, indent=2)+'\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
