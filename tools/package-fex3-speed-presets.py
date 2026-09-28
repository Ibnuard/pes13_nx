"""Package isolated Fast and full-x87 comparisons using the verified recovery binary."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'dist/pes13-fex3-sync-recovery'
PREFIX = 'switch/pes13-fex/'
INI = PREFIX + 'configuration.ini'
NRO_SHA = '0f29a4ea87d8f38bfb358c58885925289b4d7dd5fa19dd9ac1f7d1fb6541db4e'
INPUT_SHA = 'eba8345652143aa0e91c26e47f7c7459e4dd1d798b74e84bbc1e5f484d5f5eea'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError(f'Unexpected SHA256: {path}')
    return data


def ini_values(data):
    result = {}
    for line in data.decode('utf-8').splitlines():
        line = re.split('[#;]', line, 1)[0].strip()
        if not line or line.startswith('['):
            continue
        key, value = [s.strip() for s in line.split('=', 1)]
        if key in result or value not in ('0', '1'):
            raise ValueError(f'Duplicate key or invalid boolean: {key}')
        result[key] = int(value)
    return result


def main():
    base_manifest_bytes = (BASE / 'manifest.json').read_bytes()
    base_manifest = json.loads(base_manifest_bytes)
    payload = {name: checked(BASE / name, digest)
               for name, digest in base_manifest['files'].items()}
    assert len(payload) == 5 and sha(payload[PREFIX + 'pes13-fex.nro']) == NRO_SHA
    assert b'pes13-fex3-sync-recovery' in payload[PREFIX + 'pes13-fex.nro']
    assert base_manifest['targeted_wake'] is False
    assert base_manifest['dxvk_max_frame_rate'] == -1
    assert base_manifest['dxvk_max_frame_latency'] == 1
    before = ini_values(payload[INI])
    assert (before['run_guest_tests'], before['fex_fast'], before['fex_fastest'],
            before['fex_targeted_wake']) == (0, 1, 1, 0)
    source_ini = payload[INI].decode('utf-8')
    source_ini = source_ini.replace(
        '# Self-suspend candidate: restores the pre-team-sync Fastest profile for PES.',
        '# Speed diagnosis: restart between presets; runtime remains sync-recovery.')
    validation = {name: checked(BASE / name, digest)
                  for name, digest in base_manifest['validation_sha256'].items()}
    for name, data in validation.items():
        report = json.loads(data)
        assert report['passed'], name
        if 'native_elf_sha256' in report:
            assert report['native_elf_sha256'] == base_manifest['native_elf_sha256'], name
    getters = json.loads(validation['validation/fast-native-tests.json'])
    assert getters['dll_sha256'] == sha(payload[PREFIX + 'drive_c/windows/system32/libwow64fex.dll'])
    assert any('real FEX typed config getters' in s for s in getters['checks'])
    local = ROOT / 'local/fex3/sync-recovery-result'
    checked(local / 'fex-runtime.log', INPUT_SHA)
    analysis = (local / 'analysis.json').read_bytes()
    assert json.loads(analysis)['input_sha256'] == INPUT_SHA
    docs = (ROOT / 'docs/FEX3-SPEED-PRESETS.md').read_bytes()
    common = dict(validation)
    common['validation/base-manifest.json'] = base_manifest_bytes
    common['analysis.json'] = analysis
    common['FEX3-SPEED-PRESETS.md'] = docs
    common['THIRD_PARTY.md'] = (BASE / 'THIRD_PARTY.md').read_bytes()
    common.update({p.relative_to(BASE).as_posix(): p.read_bytes()
                   for p in (BASE / 'licenses').rglob('*') if p.is_file()})
    result = []
    for profile, fast in (('fast', 1), ('control', 0)):
        candidate = dict(payload)
        ini, count = re.subn(r'^fex_fastest=1$', 'fex_fastest=0', source_ini, flags=re.M)
        assert count == 1
        if not fast:
            ini, count = re.subn(r'^fex_fast=1$', 'fex_fast=0', ini, flags=re.M)
            assert count == 1
        candidate[INI] = ini.encode('utf-8')
        expected = dict(before, fex_fast=fast, fex_fastest=0)
        assert ini_values(candidate[INI]) == expected
        assert [name for name in payload if candidate[name] != payload[name]] == [INI]
        manifest = {
            'package': f'pes13-fex3-speed-{profile}',
            'build': base_manifest['build'],
            'kind': 'configuration-only controlled experiment',
            'runtime_rebuilt': False,
            'hardware_tested': False,
            'input_log_sha256': INPUT_SHA,
            'native_elf_sha256': base_manifest['native_elf_sha256'],
            'fex_commit': base_manifest['fex_commit'],
            'preset': profile, 'x87_bits': 64 if fast else 80,
            'tso_scalar_vector_memcpy': True,
            'dxvk_max_frame_rate': -1, 'dxvk_max_frame_latency': 1,
            'guest_clock_scaled': False, 'targeted_wake': False,
            'zip_created': False, 'changed_payload_files': [INI],
            'files': {name: sha(data) for name, data in candidate.items()},
            'inherited_validation_sha256': base_manifest['validation_sha256'],
            'packaging_checks': [
                'Five payload files; only the preset INI differs from sync-recovery',
                'NRO, FEX/ntdll DLLs and DXVK configuration are byte-identical to base',
                'Explicit boolean keys, no duplicates; guest tests and targeted wake off',
                'Seven existing validation reports and actual FEX profile getters match binaries',
                'Original input log digest and base package preserved',
            ],
        }
        files = dict(common, **candidate)
        files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
        files['README.txt'] = (
            f'PES13-NX FEX3 speed comparison: {profile.upper()} (no ZIP)\n\n'
            'Ini eksperimen preset, bukan NRO baru. Runtime tetap sync-recovery.\n'
            'A Fast diuji dulu; B Control hanya pembanding presisi penuh bila perlu.\n'
            'Tutup HOME -> X. Copy folder switch ke root SD dan timpa 5 file termasuk INI.\n'
            'Forwarder tetap switch/pes13-fex/pes13-fex.nro. Tidak ada game/save di paket.\n'
            f'Log: [BUILD] pes13-fex3-sync-recovery dan [FEX3-PRESET] {profile} ...\n'
            f'fex_fast={fast}; fex_fastest=0; fex_targeted_wake=0.\n'
            'DXVK limiter, frame latency, guest clock dan sinkronisasi native sama dengan base.\n\n'
            'Tes kedua preset dengan CPU-only OC yang sama sejak aplikasi dibuka.\n'
            'Gunakan setting durasi match/game speed, tim dan stadion yang sama.\n'
            'Saat bola dimainkan, catat perubahan jam scoreboard selama 30 detik nyata.\n'
            'Hindari replay/pause/set piece pada interval pengukuran. Simpan log sebelum restart.\n'
            'FPS yang turun saja tidak membuktikan speed sudah benar. Control bisa lebih lambat.\n'
            'Jangan timpa settings.dat atau cache untuk tes ini.\n\n'
            'Rollback: pakai INI sync-recovery, atau fex_fast=1 dan fex_fastest=1 lalu restart.\n'
            'Belum teruji di Switch; bukan klaim bug 2x atau stutter sudah selesai.\n'
        ).encode()
        dest = ROOT / 'dist' / manifest['package']
        assert dest.resolve().is_relative_to((ROOT / 'dist').resolve())
        assert not dest.with_suffix('.zip').exists()
        existing = {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}
        if not existing <= files.keys():
            raise ValueError(f'Unexpected files preserved: {existing - files.keys()}')
        for name, data in files.items():
            path = dest / name
            assert path.resolve().is_relative_to(dest.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            checked(path, sha(data))
        assert sum(name.endswith('.nro') for name in candidate) == 1
        result.append({'path': str(dest), 'manifest': manifest})
    # Do not alter the last tested package while producing either candidate.
    for name, digest in base_manifest['files'].items():
        checked(BASE / name, digest)
    (local / 'speed-packages.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
