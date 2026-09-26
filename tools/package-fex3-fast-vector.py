"""Verify and stage the paired Fast-vector NRO/DLL experiment without a ZIP."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/fast-vector'
BASE = ROOT / 'dist/pes13-fex3-speed-fast'
DEST = ROOT / 'dist/pes13-fex3-fast-vector'
PREFIX = 'switch/pes13-fex/'
INPUT_SHA = '7b9793cb70c2feedf9776aad193c2978d0b6192f81982b37c3c8a3f37eb21bcd'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def checked(path, digest):
    data = path.read_bytes()
    assert sha(data) == digest, f'Unexpected SHA256: {path}'
    return data


def changed(before, after):
    assert before.keys() == after.keys()
    return sorted(key for key in before if before[key] != after[key])


def ini_values(data):
    values = {}
    for line in data.decode().splitlines():
        line = re.split('[#;]', line, 1)[0].strip()
        if not line or line.startswith('['):
            continue
        key, value = (s.strip() for s in line.split('=', 1))
        assert key not in values and value in ('0', '1'), line
        values[key] = int(value)
    return values


def main():
    base = read_json(BASE / 'manifest.json')
    payload = {name: checked(BASE / name, digest) for name, digest in base['files'].items()}
    assert len(payload) == 5 and base['preset'] == 'fast'
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    patched = read_json(WORK / 'runtime/wine-patches.json')['native-source']
    module = read_json(WORK / 'module/build.json')
    previous = read_json(ROOT / 'local/fex3/sync-recovery/runtime/runtime-build.json')
    previous_module = read_json(ROOT / 'local/fex3/self-suspend/module/build.json')
    previous_patched = read_json(ROOT / 'local/fex3/sync-recovery/runtime/wine-patches.json')['native-source']
    assert base['native_elf_sha256'] == previous['native_elf_sha256']
    assert module['fex_commit'] == previous_module['fex_commit'] == base['fex_commit']
    assert changed(previous['patch_sources'], runtime['patch_sources']) == ['tools/fex_wine_patches.py']
    assert changed(previous['adapter_sources'], runtime['adapter_sources']) == [
        'horizon_host.h', 'horizon_jit.c', 'module_profile.cpp']
    assert changed(previous_module['adapter_sources'], module['adapter_sources']) == [
        'src/fex/horizon_host.h', 'src/fex/module_profile.cpp']
    assert changed(previous_patched, patched) == ['wine-nx-probe/source/runtime.c']
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256'):
        assert runtime[key] == previous[key], key
    for path, digest in runtime['patch_sources'].items():
        checked(ROOT / path, digest)
    for name, digest in runtime['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
    for path, digest in module['adapter_sources'].items():
        checked(ROOT / path, digest)
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']
    checked(WORK / 'runtime/wine-nx-runtime.elf', runtime['native_elf_sha256'])
    payload[PREFIX + 'pes13-fex.nro'] = checked(WORK / 'runtime/pes13-fex.nro', runtime['nro_sha256'])
    payload[PREFIX + 'drive_c/windows/system32/libwow64fex.dll'] = checked(
        WORK / 'module/libwow64fex.dll', module['sha256'])
    assert b'pes13-fex3-fast-vector' in payload[PREFIX + 'pes13-fex.nro']
    assert b'[FEX3-PRESET] fast-vector x87=64 scalar_tso=1 vector_tso=0 memcpy_tso=1' in payload[
        PREFIX + 'drive_c/windows/system32/libwow64fex.dll']
    checked(WORK / 'runtime/ntdll.dll', base['files'][PREFIX + 'drive_c/windows/system32/ntdll.dll'])
    ini_name = PREFIX + 'configuration.ini'
    before_ini = ini_values(payload[ini_name])
    assert (before_ini['fex_fast'], before_ini['fex_fastest'], before_ini['run_guest_tests'],
            before_ini['fex_targeted_wake']) == (1, 0, 0, 0)
    ini = payload[ini_name].decode().replace(
        '# Speed diagnosis: restart between presets; runtime remains sync-recovery.',
        '# Fast-vector experiment. Restart after any preset edit.')
    ini += ('\n# Vector-only ordering relaxation. 0 restores original Fast on this NRO.\n'
            '# Applies only with fex_fast=1 and fex_fastest=0.\nfex_relaxed_vectors=1\n')
    payload[ini_name] = ini.encode()
    assert ini_values(payload[ini_name]) == dict(before_ini, fex_relaxed_vectors=1)
    delta = changed(base['files'], {name: sha(data) for name, data in payload.items()})
    assert delta == sorted([ini_name, PREFIX + 'pes13-fex.nro',
                            PREFIX + 'drive_c/windows/system32/libwow64fex.dll'])

    reports = {}
    for name in ('frame', 'pipeline', 'pipeline-binary', 'sync', 'sync-binary',
                 'self-suspend-binary', 'fast-native'):
        data = (WORK / f'{name}-tests.json').read_bytes()
        report = json.loads(data)
        assert report['passed'] and report['hardware_tested'] is False, name
        if 'native_elf_sha256' in report:
            assert report['native_elf_sha256'] == runtime['native_elf_sha256'], name
        if name == 'fast-native':
            assert report['dll_sha256'] == module['sha256']
            assert any('fast-vector' in s for s in report['checks'])
        if name == 'frame':
            assert report['runtime_c_sha256'] == patched['wine-nx-probe/source/runtime.c']
            assert report['vulkan_c_sha256'] == patched['dlls/win32u/vulkan.c']
        for path, digest in report.get('patched_source_sha256', {}).items():
            assert patched[path] == digest, path
        for path, digest in report.get('source_sha256', {}).items():
            checked(ROOT / path, digest)
        reports[f'validation/{name}-tests.json'] = data
    analysis = (ROOT / 'local/fex3/fast-result/analysis.json').read_bytes()
    assert json.loads(analysis)['input_sha256'] == INPUT_SHA
    checked(ROOT / 'local/fex3/fast-result/fex-runtime-fast.log', INPUT_SHA)
    manifest = {
        'build': DEST.name, 'hardware_tested': False, 'host_abi': 3,
        'fex_commit': module['fex_commit'], 'preset': 'fast-vector', 'profile': 3,
        'x87_bits': 64, 'scalar_tso': True, 'vector_tso': False, 'memcpy_tso': True,
        'guest_clock_scaled': False, 'targeted_wake': False,
        'dxvk_max_frame_rate': -1, 'dxvk_max_frame_latency': 1,
        'zip_created': False, 'input_log_sha256': INPUT_SHA,
        'user_reported_cpu_oc': 'constant throughout Fast baseline run',
        'native_elf_sha256': runtime['native_elf_sha256'],
        'files': {name: sha(data) for name, data in payload.items()},
        'validation_sha256': {name: sha(data) for name, data in reports.items()},
        'changed_payload_files': delta,
        'control': 'fex_relaxed_vectors=0; retain fex_fast=1 and fex_fastest=0; restart',
        'baseline_preserved': str(BASE.relative_to(ROOT)),
        'fps_gain_measured': False, 'game_speed_fix_verified': False,
    }
    files = dict(payload, **reports)
    files.update({
        'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        'analysis.json': analysis,
        'FEX3-FAST-VECTOR.md': (ROOT / 'docs/FEX3-FAST-VECTOR.md').read_bytes(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'validation/runtime-build.json': (WORK / 'runtime/runtime-build.json').read_bytes(),
        'validation/module-build.json': (WORK / 'module/build.json').read_bytes(),
        'README.txt': (
            'PES13-NX FEX3 Fast-vector (folder only, no ZIP)\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch ke root SD dan timpa semua 5 file.\n'
            'NRO dan libwow64fex.dll adalah pasangan baru; timpa configuration.ini juga.\n'
            'Forwarder tetap switch/pes13-fex/pes13-fex.nro. Game/save/settings.dat tetap existing.\n\n'
            'Perubahan dari Fast: hanya vector TSO off; scalar dan REP TSO tetap on.\n'
            'x87, clock game, DXVK, frame latency dan self-suspend tetap sama.\n'
            'Log harus: [BUILD] pes13-fex3-fast-vector; [FEX3-PRESET] fast-vector ... vector_tso=0.\n'
            'Tes dengan CPU OC yang sama sepanjang run dan match settings yang sama.\n'
            'Perhatikan FPS/kamera sekaligus kecepatan scoreboard setelah kick-off dan event.\n'
            'Simpan fex-runtime.log sebelum restart.\n\n'
            'Control/rollback opsi: ubah HANYA fex_relaxed_vectors=0 lalu restart.\n'
            'Itu mengembalikan Fast pada NRO/DLL yang sama; log harus fast ... vector_tso=1.\n'
            'Jika gerakan 2x/hang muncul lagi, gunakan control ini.\n'
            'Rollback binary penuh: folder pes13-fex3-speed-fast sebelumnya masih utuh.\n\n'
            'Build dan pemeriksaan lokal lulus. Performa/kompatibilitas di Switch belum teruji.\n'
        ).encode(),
    })
    files.update({p.relative_to(BASE).as_posix(): p.read_bytes()
                  for p in (BASE / 'licenses').rglob('*') if p.is_file()})
    assert DEST.resolve().is_relative_to((ROOT / 'dist').resolve())
    assert not DEST.with_suffix('.zip').exists()
    existing = {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()}
    assert existing <= files.keys(), f'Preserving unexpected files: {existing - files.keys()}'
    for name, data in files.items():
        path = DEST / name
        assert path.resolve().is_relative_to(DEST.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        checked(path, sha(data))
    assert sum(name.endswith('.nro') for name in payload) == 1
    for name, digest in base['files'].items():
        checked(BASE / name, digest)
    (WORK / 'package.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'directory': str(DEST), 'manifest': manifest}, indent=2))


if __name__ == '__main__':
    main()
