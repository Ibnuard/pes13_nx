"""Package Kit17 DXVK with the exact Kit16 FEX/Kit15 host and rollback."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def body(s, signature):
    start = s.index(signature)
    end = s.index('{', start) + 1
    depth = 1
    while depth:
        depth += (s[end] == '{') - (s[end] == '}')
        end += 1
    return s[start:end]


def dependency_licenses(work, toolchain):
    paths = ('include/native/directx/COPYING.MinGW-w64.txt', 'include/openvr/LICENSE',
        'include/vulkan/LICENSE.md', 'include/spirv/LICENSE',
        'subprojects/dxbc-spirv/LICENSE', 'subprojects/dxbc-spirv/submodules/spirv_headers/LICENSE',
        'subprojects/libdisplay-info/LICENSE')
    for path in paths:
        yield work / 'source' / path, 'licenses/kit17-dxvk/' + path
    for path in ('LICENSE.TXT', 'i686-w64-mingw32/share/mingw32/COPYING',
                 'i686-w64-mingw32/share/mingw32/COPYING.MinGW-w64.txt',
                 'i686-w64-mingw32/share/mingw32/COPYING.MinGW-w64-runtime.txt',
                 'i686-w64-mingw32/share/mingw32/COPYING.winpthreads.txt',
                 'i686-w64-mingw32/share/mingw32/COPYING.winstorecompat.txt'):
        yield toolchain / path, 'licenses/kit17-toolchain/' + path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('base', 'module', 'work', 'toolchain', 'official', 'evidence', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    a.output.resolve().relative_to((ROOT / 'dist').resolve())
    assert not a.output.exists(), 'Use a new dist subdirectory'
    base = json.loads((a.base / 'manifest.json').read_text())
    build = json.loads((a.module / 'build.json').read_text())
    prepared = json.loads((a.module / 'prepared.json').read_text())
    tests = json.loads((a.work / 'tests/tests.json').read_text())
    analysis = json.loads((a.evidence / 'device-analysis.json').read_text())
    assert base['passed'] and base['kind'] == 'kit16-decoder-capacity'
    assert build['built'] and build['kind'] == 'kit17-dxvk-memory'
    assert sha(a.module / 'prepared.json') == build['prepared_sha256']
    assert sha(a.module / 'd3d9.dll') == build['dll_sha256']
    assert build['commit'] == prepared['commit'] == 'b1a1c99ab52b687cf950d62c88bc2fa316b41663'
    assert b'3.1.1-pes13-kit17' in (a.module / 'd3d9.dll').read_bytes()
    for name, digest in build['scripts'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in base['files'].items():
        assert sha(a.base / name) == digest, name
    for name, change in prepared['changes'].items():
        assert sha(a.work / 'source' / name) == change['after'] == prepared['candidate'][name], name
        assert prepared['original'][name] == change['before'], name
    assert tests['passed'] and tests['asan_ubsan'] and tests['pressure_cases'] == 768
    for name, digest in tests['sources'].items():
        assert sha(ROOT / name) == digest, name
    # Bind the host harness receipt to the same bodies compiled into the DLL.
    tested = {
        'pool': ('src/dxvk/dxvk_memory.h', '  struct DxvkMemoryPool {', ';'),
        'chunk': ('src/dxvk/dxvk_memory.cpp', '  bool DxvkMemoryAllocator::allocateChunkInPool(', ''),
        'image': ('src/dxvk/dxvk_image.cpp', '  Rc<DxvkResourceAllocation> DxvkImage::assignStorageWithUsage(', ''),
        'buffer': ('src/dxvk/dxvk_buffer.h', '    Rc<DxvkResourceAllocation> assignStorage(Rc<DxvkResourceAllocation>&& slice)', ''),
    }
    for name, (path, signature, suffix) in tested.items():
        value = body((a.work / 'source' / path).read_text(), signature) + suffix
        assert hashlib.sha256(value.encode()).hexdigest() == tests['records']['candidate']['bodies'][name], name
    assert analysis['passed'] and analysis['self_terminated']
    assert sha(a.evidence / 'kit16-device.log') == analysis['input_sha256']
    assert sha(a.official) == analysis['dll_sha256']
    for name, digest in analysis['sources'].items():
        assert sha(ROOT / name) == digest, name

    # Check the actual staged renderer against the staged runtime, including its
    # API-set schema. This checker validates exports and forwarders recursively.
    fixture = a.module / 'payload-check'
    assert sha(fixture / 'drive_c/PES13/d3d9.dll') == build['dll_sha256']
    import_report = a.module / 'imports-package.json'
    subprocess.run([sys.executable, str(ROOT / 'tools/check_payload.py'), str(fixture),
        '--dxvk', '--entry', 'd3d9.dll', '--output', str(import_report)], check=True)
    imports = json.loads(import_report.read_text())
    assert imports['static_link_check_passed'] and not imports['issues']
    import_receipt = dict(passed=True, dll_sha256=build['dll_sha256'],
        checker_sha256=sha(ROOT / 'tools/check_payload.py'), report_sha256=sha(import_report),
        files={x.relative_to(fixture).as_posix(): sha(x) for x in fixture.rglob('*') if x.is_file()},
        limits=imports['limits'])

    a.output.mkdir(parents=True)
    def copy(src, name):
        dst = a.output / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Keep the licenses, source and verification material accompanying the
    # exact inherited FEX/native binaries. Do not inherit older rollback files.
    for name in base['files']:
        if name == 'README.txt' or name.startswith(('rollback/', 'switch/')):
            continue
        copy(a.base / name, name)
    nro = 'switch/pes13-fex/pes13-fex.nro'
    fex = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
    renderer_paths = [
        'switch/pes13-fex/launcher/renderers/dxvk-3.1.1/d3d9.dll',
        'switch/pes13-fex/drive_c/dxvk/d3d9.dll',
        'switch/pes13-fex/drive_c/PES13/d3d9.dll',
    ]
    for name in (nro, fex):
        copy(a.base / name, name)
        copy(a.base / name, 'rollback/' + name)
    for name in renderer_paths:
        copy(a.module / 'd3d9.dll', name)
        copy(a.official, 'rollback/' + name)
    copy(a.base / 'manifest.json', 'evidence/kit17/kit16-manifest.json')
    for name in ('build.json', 'prepared.json', 'imports-package.json'):
        copy(a.module / name, 'evidence/kit17/' + name)
    copy(a.work / 'tests/tests.json', 'evidence/kit17/host-tests.json')
    for path in (a.work / 'tests').rglob('*.log'):
        copy(path, 'evidence/kit17/tests/' + path.relative_to(a.work / 'tests').as_posix())
    for name in ('device-analysis.json', 'kit16-device.log'):
        copy(a.evidence / name, 'evidence/kit17/' + name)
    (a.output / 'evidence/kit17/import-receipt.json').write_text(json.dumps(import_receipt, indent=2) + '\n')
    for name in prepared['changes']:
        copy(a.work / 'source' / name, 'source/kit17/dxvk/' + name)
    copy(a.work / 'source/LICENSE', 'licenses/DXVK-Kit17-LICENSE.txt')
    for source, name in dependency_licenses(a.work, a.toolchain):
        copy(source, name)
    copy(a.work / 'cross-x32.txt', 'source/kit17/cross-x32.txt')
    for name in ('tools/build-kitserver-dxvk-memory.py', 'tools/dxvk_kit17_memory.py',
                 'tools/package-kitserver-dxvk-memory.py', 'tools/analyze-kit16-dxvk.py',
                 'tools/check_payload.py', *tests['sources']):
        copy(ROOT / name, 'source/kit17/' + name)
    for name in ('KITSERVER-KIT17-DXVK-MEMORY.md', 'AS39-EXPERIMENT.md', 'AS39-LOW-WINDOW.md'):
        copy(ROOT / 'docs' / name, 'docs/' + name)
    (a.output / 'README.txt').write_text('''Kit17 - DXVK memory allocation / prematch to kick-off

Log Kit16: kegagalan alokasi Vulkan mulai detik 139.6; detik 188.8 DXVK
membaca storage kosong dan proses berhenti dengan c0000005. Kit17 memakai
chunk normal lebih kecil (maksimal 8 MiB), retry sampai ukuran kebutuhan,
dan guard storage kosong. Kebutuhan resource besar tetap dialokasikan penuh.

Build, tes alokasi lokal, dan pemeriksaan import Wine lulus.
BELUM diuji pada Switch; keberhasilan kick-off/FPS belum terukur.

PASANG
1. Tutup PES lewat HOME > X > Close.
2. Salin folder switch/ ke root SD dan timpa KELIMA file yang disertakan.
3. Gunakan NSP 32-bit no-alias yang biasa. Pilih Default DXVK / DXVK 3.1.1;
   GPL Async memiliki DLL lain dan tidak memakai perbaikan ini.
4. Tetap gunakan Medium, patch dan clock yang sama. Buka Debug launch,
   lalu Exhibition > game plan > kick-off. Kirim fex-runtime.log.
5. Jika macet dan HOME merespons, tunggu sekitar 15 detik lalu tutup.

NRO masih persis Kit15 (launcher 0.3.9-kit15), FEX masih Kit16. Perubahan
Kit17 ada di d3d9.dll, termasuk sumber renderer launcher agar tidak tertimpa
DLL lama. Tiga lokasi d3d9.dll harus ikut disalin. Preset dan save tidak diubah.
Launch biasa tetap mengikuti kebijakan produksi tanpa log diagnostik.

Check runtime dapat menandai DLL eksperimen sebagai changed. Repair runtime
akan memulihkan DLL produksi; salin kembali paket ini jika Repair digunakan.

ROLLBACK: salin rollback/switch/ ke root SD untuk mengembalikan renderer
DXVK 3.1.1 resmi dengan FEX Kit16/NRO Kit15. Tidak ada ZIP atau file game.

Ini belum port AS39. Audit low-window dan batas memori ada di
docs/AS39-LOW-WINDOW.md; tidak ada kernel/boot/NSP baru dalam paket ini.
''', encoding='utf-8')
    files = {x.relative_to(a.output).as_posix(): sha(x) for x in sorted(a.output.rglob('*')) if x.is_file()}
    payload = [nro, fex, *renderer_paths]
    assert sorted(n for n in files if n.startswith('switch/')) == sorted(payload)
    assert files[nro] == base['nro_sha256'] and files[fex] == base['fex_sha256']
    for name in renderer_paths:
        assert files[name] == build['dll_sha256']
        assert files['rollback/' + name] == sha(a.official)
    manifest = dict(passed=True, kind='kit17-dxvk-memory', version='3.1.1-pes13-kit17',
        nro_version=base['nro_version'], nro_unchanged=True, fex_unchanged=True,
        nro_sha256=base['nro_sha256'], fex_sha256=base['fex_sha256'],
        native_elf_sha256=base['native_elf_sha256'], dxvk_sha256=build['dll_sha256'],
        rollback_dxvk_sha256=sha(a.official), renderer='Default DXVK',
        address_mode='32-bit no-alias', hardware_tested=False, freeze_fixed=False,
        files=files)
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for name, digest in files.items():
        assert sha(a.output / name) == digest, name
    print(json.dumps(dict(directory=str(a.output), verified_files=len(files),
                         payload_files=payload, dxvk_sha256=build['dll_sha256'])))


if __name__ == '__main__':
    main()
