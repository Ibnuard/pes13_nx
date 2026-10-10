"""Package LW6 settings routing with the exact tested LW5 NRO as rollback."""
import argparse, difflib, hashlib, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NRO = 'switch/pes13-fex/pes13-low-window.nro'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'previous-runtime', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--previous', type=Path, default=ROOT/'dist/pes13-low-window-v5-asset-trace')
    p.add_argument('--evidence', type=Path, default=ROOT/'local/lw6-settings')
    a = p.parse_args(); a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not a.output.exists(), 'Use a fresh output directory'
    build, previous = read(a.runtime/'build.json'), read(a.previous/'package.json')
    assert build['built'] and build['version'] == '0.3.9-lw6'
    assert previous['version'] == '0.3.9-lw5' and previous['abi'] == 'fxtmem-v1'
    assert sha(a.runtime/'pes13-fex.nro') == build['nro_sha256']
    assert sha(a.runtime/'native-build/wine-nx-runtime.elf') == build['elf_sha256']
    assert sha(a.previous/NRO) == previous['payload'][NRO] == read(a.previous_runtime/'build.json')['nro_sha256']
    for rel, digest in previous['files'].items():
        if rel.startswith(('source/', 'licenses/')): assert sha(a.previous/rel) == digest, rel
    for rel, digest in build['inputs'].items(): assert sha(ROOT/rel) == digest, rel
    for name in ('binary-tests.json', 'settings-binary.json'):
        result = read(a.evidence/name)
        assert result['passed'] and result['elf_sha256'] == build['elf_sha256'], name
    host = read(a.evidence/'settings-host.json'); assert host['passed']
    for rel, digest in host['sources'].items(): assert sha(ROOT/rel) == digest, rel
    baseline = read(a.evidence/'baseline-settings.json')
    assert baseline['passed'] and baseline['regression_reproduced']
    assert baseline['elf_sha256'] == previous['native_elf_sha256']
    old, new = (read(x/'prepared.json') for x in (a.previous_runtime, a.runtime))
    native = {n for n in set(old['after']) | set(new['after']) if old['after'].get(n) != new['after'].get(n)}
    feature = {n for n in set(old['feature_after']) | set(new['feature_after'])
               if old['feature_after'].get(n) != new['feature_after'].get(n)}
    assert native == {'wine-nx-probe/source/runtime.c', 'wine-nx-probe/CMakeLists.txt',
                      'dlls/ntdll/unix/file.c', 'dlls/ntdll/unix/pes_settings_route.h'}, native
    assert feature == {'src/runtime/fextendo_presets.h'}, feature
    for folder, key in (('native-source', 'after'), ('feature', 'feature_after')):
        for rel, digest in new[key].items(): assert sha(a.runtime/folder/rel) == digest, rel
    a.output.mkdir(parents=True)
    def put(rel, data):
        target = a.output/rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    def copy(source, rel): put(rel, source.read_bytes())
    def jsonfile(rel, data): put(rel, (json.dumps(data, indent=2)+'\n').encode())
    copy(a.runtime/'pes13-fex.nro', NRO); copy(a.previous/NRO, 'rollback/'+NRO)
    for name in ('build.json', 'prepared.json'): copy(a.runtime/name, 'evidence/'+name)
    for name in ('binary-tests.json', 'settings-binary.json', 'settings-host.json',
                 'baseline-settings.json', 'diagnosis.json'):
        copy(a.evidence/name, 'evidence/'+name)
    copy(a.previous/'package.json', 'evidence/lw5-package.json')
    # Keep the previous complete corresponding-source/license chain for both NROs.
    for directory in ('source', 'licenses'):
        if (a.previous/directory).exists(): shutil.copytree(a.previous/directory, a.output/directory/'lw5-baseline')
    sources = set(build['inputs']) | {'tools/package-pes-low-window-settings.py',
        'tests/pes_settings_route.c', 'tests/pes_settings_host.py', 'tests/pes_settings_binary.py',
        'tests/fextendo_preset_failures.c', 'tests/fextendo_ui.c',
        'tests/pes_low_window_binary.py', 'docs/PES13-LOW-WINDOW-V6-SETTINGS.md'}
    for rel in sorted(sources): copy(ROOT/rel, 'source/lw6/'+rel)
    delta = []
    for folder, names in (('native-source', native), ('feature', feature)):
        for rel in sorted(names):
            before, after = a.previous_runtime/folder/rel, a.runtime/folder/rel
            delta.extend(difflib.unified_diff(before.read_text().splitlines(keepends=True) if before.exists() else [],
                after.read_text().splitlines(keepends=True), fromfile='a/'+folder+'/'+rel, tofile='b/'+folder+'/'+rel))
            copy(after, 'source/generated/'+folder+'/'+rel)
    put('source/lw6.patch', ''.join(delta).encode())
    copy(ROOT/'docs/PES13-LOW-WINDOW-V6-SETTINGS.md', 'DETAILS.txt')
    put('README.txt', ('LW6 - preset launcher untuk settings.dat dengan nama patch berbeda.\n\n'
        'Tutup game. Salin hanya folder switch ke root SD dan timpa NRO low-window.\n'
        'Gunakan forwarder low-window yang sama; tidak perlu NSP/KIP baru.\n'
        'Pilih preset grafis yang diinginkan, lalu Debug launch untuk tes pertama.\n'
        'Log yang diharapkan: [LW6-SETTINGS] alias nama patch ke preset KONAMI asli;\n'
        '[SETTINGS-VERIFY] frame_skip=0 xinput=1, serta live settings sesuai preset.\n'
        'Cek controller dan kecepatan gameplay; kirim fex-runtime.log terbaru.\n\n'
        'File save/OPTION/EDIT, game, runtime DLL dan config Kitserver tidak ditimpa.\n'
        'Preset tetap dinamis; perubahan Graphics diterapkan saat launch berikutnya.\n'
        'Launch biasa tetap tanpa log diagnostik. Folder rollback/switch memulihkan LW5.\n'
        'Build, sanitizer dan tes ARM64 selesai. Hasil gameplay masih perlu tes Switch.\n'
        'Folder siap salin, tanpa ZIP. Jangan salin seluruh paket ke SD.\n').encode())
    files = {x.relative_to(a.output).as_posix():sha(x) for x in sorted(a.output.rglob('*')) if x.is_file()}
    payload = {n:d for n,d in files.items() if n.startswith('switch/')}
    assert payload == {NRO:build['nro_sha256']}
    assert not any(a.output.rglob('*.dll')) and not any(a.output.rglob('*.zip')) and not any(a.output.rglob('*.nsp'))
    jsonfile('package.json', dict(built=True, version=build['version'], abi='fxtmem-v1', hardware_tested=False,
        settings_fix_device_verified=False, game_assets_changed=False, fex_changed=False, dxvk_changed=False,
        memory_implementation_changed=False, clock_scaled=False, native_elf_sha256=build['elf_sha256'],
        previous_nro_sha256=previous['payload'][NRO],
        change='Resolve renamed patch settings.dat to launcher preset; enforce both XInput bits and frame skip off.',
        payload=payload, files=files))
    files['package.json'] = sha(a.output/'package.json')
    put('SHA256SUMS.txt', ''.join(f'{d}  {n}\n' for n,d in sorted(files.items())).encode())
    for rel, digest in files.items(): assert sha(a.output/rel) == digest, rel
    print(f'Packaged LW6: {len(files)} verified files, NRO-only install and exact LW5 rollback; no ZIP.')


if __name__ == '__main__': main()
