"""Assemble a copy-ready PES low-window experiment beside the existing NRO."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'switch/pes13-fex/pes13-low-window.nro'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--native-baseline', type=Path, required=True)
    ap.add_argument('--baseline', type=Path, default=ROOT/'dist/pes13-kitserver-v3.9-kit17-dxvk-memory')
    ap.add_argument('--tests', type=Path, default=ROOT/'local/pes-low-window-v1/binary-tests.json')
    ap.add_argument('--hardware', type=Path, default=ROOT/'local/fextendo-memory-probe-r2/device-pass')
    ap.add_argument('--output', type=Path, default=ROOT/'dist/pes13-low-window-v1')
    a = ap.parse_args()
    a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not (a.output/'package.json').exists(), 'Package already finalized'
    build, base, tests = read(a.runtime/'build.json'), read(a.baseline/'manifest.json'), read(a.tests)
    forwarder, hardware = read(a.output/'forwarder-build.json'), read(a.hardware/'hardware-results.json')
    assert build['built'] and build['version'] == '0.3.9-lw1'
    assert tests['passed'] and tests['elf_sha256'] == build['elf_sha256']
    assert tests['normal_launch_diagnostic_io_disabled']
    assert sha(a.runtime/'native-build/wine-nx-runtime.elf') == build['elf_sha256']
    assert sha(a.runtime/'pes13-fex.nro') == build['nro_sha256'] == forwarder['runtime_nro_sha256']
    assert sha(a.native_baseline/'build-report.json') == build['baseline_receipt_sha256']
    assert forwarder['target'] == '/'+TARGET and forwarder['forwarder']['packed_exefs_verified']
    assert forwarder['forwarder']['address_bits'] == 39 and forwarder['generic_abi'] == 'fxtmem-v1'
    assert sha(a.output/'forwarders'/forwarder['forwarder']['nsp']) == forwarder['forwarder']['sha256']
    assert base['passed'] and base['kind'] == 'kit17-dxvk-memory'
    assert base['nro_sha256'] == '11f5b2a04cf7db541d30850f25f8590ffe290d900487fcc2cde93feafcbff1a7'
    assert hardware['hardware_tested'] and hardware['revision'] == 'probe-r2'
    for item in hardware['results']:
        log = a.hardware/(item['tag']+'.log')
        assert item['passed'] and sha(log) == item['sha256']
        assert 'probe-r2' in log.read_text() and '[SUMMARY] PASS' in log.read_text()
    assert {x['tag'] for x in hardware['results']} == {'control', 'optin-a', 'optin-b'}
    for rel, digest in build['inputs'].items(): assert sha(ROOT/rel) == digest, rel
    for rel, digest in build['source_changes'].items(): assert sha(a.runtime/'native-source'/rel) == digest, rel
    for rel, digest in build['feature_changes'].items(): assert sha(a.runtime/'feature'/rel) == digest, rel
    for rel, digest in base['files'].items(): assert sha(a.baseline/rel) == digest, rel

    def copy(src, rel):
        dst = a.output/rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in base['files']:
        if rel.startswith('source/'): copy(a.baseline/rel, 'source/kit17-baseline/'+rel[7:])
        elif rel.startswith('licenses/'): copy(a.baseline/rel, rel)
        elif rel.startswith('switch/') and rel.endswith('.dll'): copy(a.baseline/rel, rel)
    copy(a.runtime/'pes13-fex.nro', TARGET)
    copy(a.baseline/'switch/pes13-fex/pes13-fex.nro', 'rollback/switch/pes13-fex/pes13-fex.nro')
    copy(a.baseline/'manifest.json', 'evidence/kit17-baseline-manifest.json')
    copy(a.native_baseline/'build-report.json', 'evidence/kit15-native-baseline-build.json')
    copy(a.runtime/'build.json', 'evidence/runtime-build.json')
    copy(a.runtime/'prepared.json', 'evidence/runtime-source-hashes.json')
    copy(a.tests, 'evidence/pes-low-window-arm64.json')
    for file in a.hardware.iterdir():
        if file.is_file(): copy(file, 'evidence/probe-r2-device/'+file.name)
    scripts = ('tools/build-pes-low-window.py', 'tools/pes_low_window_patches.py',
        'tools/build-pes-low-window-forwarder.py', 'tools/package-pes-low-window.py',
        'tools/fextendo_low_window.py', 'tools/build-fextendo-memory-probe.py',
        'tools/build-fextendo-forwarder.py', 'tools/build-as39-probe.py',
        'tests/pes_low_window_binary.py', 'tests/fextendo_memory_probe_binary.py',
        'tests/as39_probe_binary.py', 'tests/fextendo_startup_binary.py',
        'tests/fextendo_virtmem_binary.py', 'tests/fextendo_fragmented_heap_binary.py',
        'tests/fextendo_scratch_pages_binary.py', 'tests/fextendo_production_binary.py',
        'tests/fextendo_silent.py', 'tests/fextendo_page_store_binary.py',
        'tests/fextendo_commit_binary.py', 'tests/fex_reservations.py')
    for rel in scripts: copy(ROOT/rel, 'source/low-window/'+rel)
    for file in (ROOT/'src/experimental/low_window').iterdir():
        if file.is_file(): copy(file, 'source/low-window/src/experimental/low_window/'+file.name)
    diffs = []
    for root, changes in (('native-source', build['source_changes']), ('feature', build['feature_changes'])):
        for rel in changes:
            old, new = a.native_baseline/root/rel, a.runtime/root/rel
            before = old.read_text().splitlines(keepends=True) if old.is_file() else []
            after = new.read_text().splitlines(keepends=True)
            diffs.extend(difflib.unified_diff(before, after, fromfile='a/'+root+'/'+rel, tofile='b/'+root+'/'+rel))
            copy(new, 'source/generated/'+root+'/'+rel)
    (a.output/'source/pes-low-window-v1.patch').write_text(''.join(diffs))
    for rel in ('docs/PES13-LOW-WINDOW-V1.md', 'docs/FEXTENDO-MEMORY-ABI-V1.md'): copy(ROOT/rel, rel)
    (a.output/'INSTALL.txt').write_text('''PES13 LOW WINDOW v1 - experimental - NRO 0.3.9-lw1

1. Gunakan boot entry FEXTendo Memory v1 TEST yang tadi lulus probe-r2.
   Kalau masih di entry tersebut, tidak perlu reboot atau mengganti kernel.
2. Salin folder switch/ dari paket ini ke root SD. Pertahankan runtime lengkap,
   game, save dan configuration.ini yang sudah ada. Ini hanya update parsial.
   NRO baru: /switch/pes13-fex/pes13-low-window.nro
   NRO lama pes13-fex.nro tidak ditimpa oleh folder switch/ ini.
3. Install forwarders/PES13-Low-Window-v1.nsp, lalu buka tile PES13 Low Window.
4. Pilih Default DXVK, gunakan preset dan clock yang sama dengan tes sebelumnya,
   lalu pilih Debug launch. Jika tile Debug belum muncul, aktifkan di Settings.
5. Uji Exhibition -> controller -> team selection -> gameplan -> kick-off.
   Jika berhasil, lanjutkan replay, bola keluar, half-time/full-time.
6. Setelah menutup game, kirim /switch/pes13-fex/fex-runtime.log dan crash.log
   bila ada, beserta posisi/waktu macet jika terjadi. Debug mencatat
   [PES13-LOWVA] v1 ready=1 beserta heap/quota sebenarnya.

Kembali ke baseline: buka tile PES biasa yang memakai pes13-fex.nro.
rollback/switch/ berisi NRO Kit15 persis, hanya diperlukan jika NRO lama
sebelumnya sudah ditimpa secara terpisah. FEX Kit16 dan DXVK Kit17 tetap sama.

Tidak ada perubahan kernel/loader, OC, preset, game, save, atau INI di paket ini.
Normal Launch tetap tanpa log diagnostik; gunakan Debug launch untuk tes awal.
Probe lulus di perangkat, build PES ini belum diuji di Switch. Hasil probe
menunjukkan heap sekitar 3.09 GiB, bukan 4 GiB RAM penuh; belum klaim FPS naik.
Rincian dan sumber: docs/PES13-LOW-WINDOW-V1.md dan source/.
''', encoding='utf-8')
    payload = {p.relative_to(a.output).as_posix(): sha(p) for p in sorted((a.output/'switch').rglob('*')) if p.is_file()}
    assert set(payload) == {TARGET, *[r for r in base['files'] if r.startswith('switch/') and r.endswith('.dll')]}
    assert len(payload) == 5 and 'switch/pes13-fex/pes13-fex.nro' not in payload
    assert not list(a.output.rglob('*.zip')) and not list(a.output.rglob('prod.keys'))
    files = {p.relative_to(a.output).as_posix(): sha(p) for p in sorted(a.output.rglob('*')) if p.is_file()}
    report = dict(built=True, host_tests_passed=True, hardware_tested_pes=False,
        generic_probe_hardware_passed=True, abi='fxtmem-v1', version='0.3.9-lw1',
        title_id=forwarder['forwarder']['title_id'], target='/'+TARGET,
        kernel_loader_changed=False, physical_heap_guarantee=False, software_guest_bias=False,
        baseline_manifest_sha256=sha(a.baseline/'manifest.json'), native_elf_sha256=build['elf_sha256'],
        fex_sha256=base['fex_sha256'], dxvk_sha256=base['dxvk_sha256'], payload=payload, files=files)
    (a.output/'package.json').write_text(json.dumps(report, indent=2)+'\n')
    files['package.json'] = sha(a.output/'package.json')
    (a.output/'SHA256SUMS.txt').write_text(''.join(f'{h}  {rel}\n' for rel, h in sorted(files.items())))
    for rel, h in files.items(): assert sha(a.output/rel) == h, rel
    print(f'Packaged PES13 low-window v1: {len(payload)} payload files, {len(files)} verified package files; no ZIP.', flush=True)


if __name__ == '__main__': main()
