"""Stage the verified timing-audit overlay; preserve previous packages, no ZIP."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/timing-audit'
BASE = ROOT / 'dist/pes13-fex3-fast-vector'
DEST = ROOT / 'dist/pes13-fex3-timing-audit'
PREFIX = 'switch/pes13-fex/'
INPUT_SHA = '915aedf3f349e20d5edde329a35a0998d0e726ab4e98ab48c9fac68d54288f11'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, digest):
    data = path.read_bytes()
    assert sha(data) == digest, f'Unexpected SHA256: {path}'
    return data


def read_json(path):
    return json.loads(path.read_text())


def delta(a, b):
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def ini_values(data):
    out = {}
    for line in data.decode().splitlines():
        line = re.split('[#;]', line, 1)[0].strip()
        if not line or line.startswith('['):
            continue
        k, v = (p.strip() for p in line.split('=', 1))
        assert k not in out and v in ('0','1')
        out[k] = int(v)
    return out


def main():
    base = read_json(BASE / 'manifest.json')
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    previous = read_json(ROOT / 'local/fex3/fast-vector/runtime/runtime-build.json')
    module = read_json(ROOT / 'local/fex3/fast-vector/module/build.json')
    patches = read_json(WORK / 'runtime/wine-patches.json')['native-source']
    prev_patches = read_json(ROOT / 'local/fex3/fast-vector/runtime/wine-patches.json')['native-source']
    assert base['native_elf_sha256'] == previous['native_elf_sha256']
    assert runtime['adapter_sources'] == previous['adapter_sources']
    assert delta(prev_patches, patches) == ['dlls/ntdll/unix/virtual.c', 'wine-nx-probe/source/runtime.c']
    assert delta(previous['patch_sources'], runtime['patch_sources']) == sorted([
        'tools/build-fex-runtime.py','tools/fex_wine_patches.py',
        'tools/fex_game_timing_patches.py','src/runtime/fex_game_timing.h',
        'src/runtime/fex_game_timing_runtime.h','src/runtime/fex_log_policy.h'])
    for key in ('ntdll_sha256','wow64_sha256','guest_sha256'):
        assert runtime[key] == previous[key]
    for path, digest in runtime['patch_sources'].items():
        checked(ROOT / path, digest)
    for name, digest in runtime['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
    for path, digest in module['adapter_sources'].items():
        checked(ROOT / path, digest)
    checked(WORK / 'runtime/wine-nx-runtime.elf', runtime['native_elf_sha256'])
    payload = {p: checked(BASE / p, digest) for p, digest in base['files'].items()}
    assert len(payload) == 5
    nro = PREFIX + 'pes13-fex.nro'
    payload[nro] = checked(WORK / 'runtime/pes13-fex.nro', runtime['nro_sha256'])
    assert b'pes13-fex3-timing-audit' in payload[nro]
    assert b'[FEX3-GCLOCK]' in payload[nro]
    assert sha(payload[PREFIX + 'drive_c/windows/system32/libwow64fex.dll']) == module['sha256']
    checked(WORK / 'runtime/ntdll.dll', runtime['ntdll_sha256'])
    ini = PREFIX + 'configuration.ini'
    before_ini = ini_values(payload[ini])
    text = payload[ini].decode().replace(
        '# Fast-vector experiment. Restart after any preset edit.',
        '# Timing audit: Fastest throughput baseline. Restart after preset edits.')
    text = text.replace('fex_fastest=0','fex_fastest=1').replace('fex_relaxed_vectors=1','fex_relaxed_vectors=0')
    text = text.replace('# Vector-only ordering relaxation. 0 restores original Fast on this NRO.',
                        '# Ignored while Fastest is active; 0 selects original Fast when Fastest=0.')
    text += ('\n# Read-only PES timing snapshots every 5s; no guest clock or frame-skip changes.\n'
             'fex_game_timing=1\n')
    payload[ini] = text.encode()
    assert ini_values(payload[ini]) == dict(before_ini, fex_fastest=1, fex_relaxed_vectors=0, fex_game_timing=1)
    files_sha = {p: sha(data) for p, data in payload.items()}
    assert delta(base['files'], files_sha) == [ini, nro]
    reports = {}
    for name in ('frame','pipeline','pipeline-binary','sync','sync-binary',
                 'self-suspend-binary','fast-native','game-timing'):
        data = (WORK / f'{name}-tests.json').read_bytes()
        report = json.loads(data)
        assert report['passed'] and report['hardware_tested'] is False, name
        if 'native_elf_sha256' in report:
            assert report['native_elf_sha256'] == runtime['native_elf_sha256'], name
        if name == 'fast-native':
            assert report['dll_sha256'] == module['sha256']
        if name == 'frame':
            assert report['runtime_c_sha256'] == patches['wine-nx-probe/source/runtime.c']
            assert report['vulkan_c_sha256'] == patches['dlls/win32u/vulkan.c']
        for path, digest in report.get('patched_source_sha256', {}).items():
            assert patches[path] == digest
        for path, digest in report.get('source_sha256', {}).items():
            checked(ROOT / path, digest)
        reports[f'validation/{name}-tests.json'] = data
    analysis = (ROOT / 'local/fex3/fast-vector-result/analysis.json').read_bytes()
    assert json.loads(analysis)['input_sha256'] == INPUT_SHA
    checked(ROOT / 'local/fex3/fast-vector-result/fex-runtime.log', INPUT_SHA)
    manifest = {
        'build': DEST.name, 'hardware_tested': False, 'host_abi': 3,
        'fex_commit': module['fex_commit'], 'preset': 'fastest', 'profile': 2,
        'x87_bits':64, 'scalar_tso':False, 'vector_tso':False, 'memcpy_tso':False,
        'game_timing_read_only':True, 'probe_period_seconds':5,
        'periodic_log_flush_batched':True, 'guest_clock_scaled':False,
        'game_frame_skipping_changed':False, 'targeted_wake':False,
        'dxvk_max_frame_rate':-1, 'dxvk_max_frame_latency':1,
        'zip_created':False, 'fps_gain_measured':False, 'game_speed_fix_verified':False,
        'input_log_sha256':INPUT_SHA, 'native_elf_sha256':runtime['native_elf_sha256'],
        'files':files_sha, 'changed_payload_files':delta(base['files'], files_sha),
        'validation_sha256':{name:sha(data) for name,data in reports.items()},
        'native_source_delta':delta(prev_patches, patches),
        'baseline_preserved':BASE.relative_to(ROOT).as_posix(),
    }
    files = dict(payload, **reports)
    files.update({
        'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),
        'analysis.json':analysis,
        'FEX3-TIMING-AUDIT.md':(ROOT/'docs/FEX3-TIMING-AUDIT.md').read_bytes(),
        'THIRD_PARTY.md':(ROOT/'THIRD_PARTY.md').read_bytes(),
        'validation/runtime-build.json':(WORK/'runtime/runtime-build.json').read_bytes(),
        'validation/wine-patches.json':(WORK/'runtime/wine-patches.json').read_bytes(),
        'validation/module-build.json':(ROOT/'local/fex3/fast-vector/module/build.json').read_bytes(),
        'README.txt':(
            'PES13-NX FEX3 timing audit - folder only, no ZIP\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch ke root SD dan timpa 5 file.\n'
            'Forwarder tetap switch/pes13-fex/pes13-fex.nro.\n'
            'Build marker: pes13-fex3-timing-audit; preset: fastest.\n\n'
            'Paket ini mengurangi flush log per baris dan membaca timing internal PES.\n'
            'Ini BELUM fix terverifikasi untuk speed 2x atau jaminan gameplay 30 FPS.\n'
            'Game, save, settings.dat dan DXVK tetap existing.\n'
            'Jaga clock CPU/GPU/RAM konstan sepanjang run. Main melewati kick-off dan replay.\n'
            'Simpan switch/pes13-fex/fex-runtime.log sebelum membuka aplikasi lagi.\n'
            'Jika bisa, bandingkan gerak dan kenaikan jam PES selama 30 detik nyata\n'
            'dengan durasi match yang sama; jangan menghitung saat bola mati/replay.\n\n'
            'Probe bisa dimatikan lewat fex_game_timing=0 lalu restart.\n'
            'Control Fast di binary yang sama: fex_fastest=0, fex_fast=1, fex_relaxed_vectors=0.\n'
            'Folder paket sebelumnya tetap tersedia untuk rollback.\n'
            '8 laporan pemeriksaan lokal lulus; pengujian Switch masih diperlukan.\n'
        ).encode(),
    })
    files.update({p.relative_to(BASE).as_posix():p.read_bytes()
                  for p in (BASE/'licenses').rglob('*') if p.is_file()})
    assert DEST.resolve().is_relative_to((ROOT/'dist').resolve())
    assert not DEST.with_suffix('.zip').exists()
    existing = {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()}
    assert existing <= files.keys(), f'Preserving unexpected files: {existing - files.keys()}'
    for name, data in files.items():
        path = DEST/name
        assert path.resolve().is_relative_to(DEST.resolve())
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        checked(path,sha(data))
    for name,digest in base['files'].items():
        checked(BASE/name,digest)
    assert sum(name.endswith('.nro') for name in payload) == 1
    (WORK/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'directory':str(DEST),'payload_files':list(payload),
                      'tests_passed':len(reports),'nro_sha256':runtime['nro_sha256'],
                      'hardware_tested':False,'zip_created':False},indent=2))


if __name__ == '__main__':
    main()
