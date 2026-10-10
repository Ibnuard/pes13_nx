"""Package a validated NRO-only probe update, preserving the original v1 kit."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='Directory produced by --nro-only')
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--tests', type=Path, required=True)
    a = p.parse_args()
    build = json.loads((a.output / 'probe-build.json').read_text())
    baseline = json.loads((a.baseline / 'probe-build.json').read_text())
    tests = json.loads(a.tests.read_text())
    assert build['nro_only'] and build['revision'] == 'probe-r2'
    assert build['abi'] == baseline['abi'] == 'fxtmem-v1'
    assert build['target'] == baseline['target']
    assert tests['passed'] and tests['elf_sha256'] == build['probe_elf_sha256']
    assert tests['baseline_elf_sha256'] == baseline['probe_elf_sha256']
    nro = a.output / build['target'].lstrip('/')
    assert sha(nro) == build['nro_sha256']
    assert b'FEXTendo memory ABI v1 probe-r2' in nro.read_bytes()
    for rel, digest in build['source_files'].items():
        assert sha(ROOT / rel) == digest, f'Source changed since build: {rel}'
    # The original kit may now contain device logs; only validate files listed
    # by its manifest, without rewriting it or touching the attached evidence.
    verified = {}
    for line in (a.baseline / 'SHA256SUMS.txt').read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        assert sha(a.baseline / rel) == digest, f'Baseline modified: {rel}'
        verified[rel] = digest

    evidence = a.output / 'evidence-v1'
    evidence.mkdir(exist_ok=True)
    observations = {}
    for tag in ('control', 'optin-a', 'optin-b'):
        log = a.baseline / 'forwarders' / (tag + '.log')
        text = log.read_text()
        assert 'FEXTendo memory ABI v1 | ' + tag in text
        assert 'execute_and_backpatch=PASS' in text
        assert 'none=0000d401' in text
        assert ('aslr_base=0x8000000 ' if tag == 'control' else 'aslr_base=0x200000 ') in text
        shutil.copy2(log, evidence / log.name)
        observations[tag] = {'sha256': sha(log),
            'reported_summary': 'PASS' if '[SUMMARY] PASS' in text else 'FAIL',
            'layout_and_high_jit_passed': True, 'permission_roundtrip_passed': False}
    for rel in (*build['source_files'], 'tools/fextendo_low_window.py',
                'tests/as39_probe_binary.py', 'tests/fextendo_memory_probe_binary.py',
                'tools/package-fextendo-memory-probe.py', 'docs/FEXTENDO-MEMORY-ABI-V1.md'):
        dest = a.output / 'source' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    shutil.copytree(a.baseline / 'licenses', a.output / 'licenses', dirs_exist_ok=True)
    shutil.copy2(a.tests, a.output / 'binary-tests.json')
    (a.output / 'INSTALL.txt').write_text('''FEXTendo Memory ABI v1 - probe-r2 (NRO-only)

1. Tutup probe yang sedang berjalan.
2. Salin folder switch dari paket ini ke root SD, timpa NRO probe lama.
   Tujuan: /switch/fextendo-memory-probe/fextendo-memory-probe.nro
3. Gunakan kernel/loader v1 dan tiga tile HOME yang sudah terpasang.
   Tidak perlu install NSP lagi atau reboot jika masih memakai boot entry
   FEXTendo Memory v1 TEST. Jika sudah pindah boot entry, kembali ke entry itu.
4. Jalankan CONTROL, OPTIN-A, OPTIN-B, lalu OPTIN-A lagi. Tutup tiap tes dengan +.
   Header log/layar harus bertuliskan probe-r2, dan semua SUMMARY diharapkan PASS.
5. Kirim control.log, optin-a.log, optin-b.log dari
   /switch/fextendo-memory-probe/. A yang pertama tersimpan di optin-a.previous.log.

Perbaikan:
- RW pertama mengubah AliasCode menjadi AliasCodeData. Perubahan NONE/RW
  berikutnya kini memakai SetMemoryPermission sesuai aturan kernel.
- CONTROL wajib lulus tes RW/NONE/RW di 0xfffff000. Kegagalan permission
  setelah map berhasil tidak lagi dianggap sebagai penolakan mapping normal.
- Setiap API/stage dicatat terpisah; panggilan yang dilewati tidak dilaporkan
  seolah-olah sudah dipanggil.

Uji ARM64 dengan model SVC lulus. Uji fisik probe-r2 masih diperlukan.
Ini hanya update alat uji memory, bukan build PES 39-bit atau optimasi FPS.
Log v1 menunjukkan heap sekitar 3.09 GiB, bukan 4 GiB RAM fisik.
''', encoding='utf-8')
    receipt = {'revision': 'probe-r2', 'nro_sha256': sha(nro),
               'nro_only': True, 'abi_changed': False, 'game_runtime_changed': False,
               'hardware_tested_r2': False, 'host_tests_passed': True,
               'v1_device_observations': observations,
               'reuse_forwarders': baseline['forwarders'],
               'reuse_boot_sha256': {k: v for k, v in verified.items() if k.startswith('boot/')},
               'limitations': 'Generic opt-in selection works on device; corrected permissions need device rerun.'}
    (a.output / 'package.json').write_text(json.dumps(receipt, indent=2) + '\n')
    files = sorted(f for f in a.output.rglob('*') if f.is_file() and f.name != 'SHA256SUMS.txt')
    (a.output / 'SHA256SUMS.txt').write_text(''.join(f'{sha(f)}  {f.relative_to(a.output).as_posix()}\n' for f in files))
    assert list((a.output / 'switch').rglob('*.nro')) == [nro]
    assert not list(a.output.rglob('*.nsp')) and not list(a.output.rglob('*.kip'))
    print(f'Packaged {build["revision"]}: {nro.stat().st_size} bytes, {len(files)} verified files; NRO only.')


if __name__ == '__main__':
    main()
