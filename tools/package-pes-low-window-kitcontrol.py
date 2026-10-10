"""Package the tested LW4 NRO and a separate optional FSERV loading control."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

from kitserver_loading_control import prepare

ROOT = Path(__file__).resolve().parents[1]
NRO = 'switch/pes13-fex/pes13-low-window.nro'
CONFIG = 'switch/pes13-fex/drive_c/PES13/kitserver13/config.txt'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--previous-runtime', type=Path, required=True)
    ap.add_argument('--previous', type=Path, default=ROOT/'dist/pes13-low-window-v3-live-settings')
    ap.add_argument('--evidence', type=Path, default=ROOT/'local/pes-low-window-v4-kitcontrol')
    ap.add_argument('--game', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert not a.output.exists(), 'Use a fresh package directory'
    build, previous, tests, policy = (read(p) for p in (
        a.runtime/'build.json', a.previous/'package.json',
        a.evidence/'binary-tests.json', a.evidence/'policy-tests.json'))
    assert build['built'] and build['version'] == '0.3.9-lw4'
    assert previous['version'] == '0.3.9-lw3' and previous['abi'] == 'fxtmem-v1'
    for test in (tests, policy):
        assert test['passed'] and test['elf_sha256'] == build['elf_sha256']
    for key in ('normal_launch_diagnostic_io_disabled', 'lw2_pacing_debug_gate_checked',
                'lw3_live_settings_and_vk_attribution_checked'): assert tests[key]
    assert sha(a.runtime/'native-build/wine-nx-runtime.elf') == build['elf_sha256']
    assert sha(a.runtime/'pes13-fex.nro') == build['nro_sha256']
    old_build = read(a.previous_runtime/'build.json')
    assert old_build['nro_sha256'] == previous['payload'][NRO] == sha(a.previous/NRO)
    for rel, digest in previous['files'].items(): assert sha(a.previous/rel) == digest, rel
    for rel, digest in build['inputs'].items(): assert sha(ROOT/rel) == digest, rel
    for root, key in (('native-source', 'source_changes'), ('feature', 'feature_changes')):
        for rel, digest in build[key].items(): assert sha(a.runtime/root/rel) == digest, rel
    old, new = (read(p/'prepared.json') for p in (a.previous_runtime, a.runtime))
    native_delta = {n for n in set(old['after']) | set(new['after']) if old['after'].get(n) != new['after'].get(n)}
    feature_delta = {n for n in set(old['feature_after']) | set(new['feature_after'])
                     if old['feature_after'].get(n) != new['feature_after'].get(n)}
    assert native_delta == {'wine-nx-probe/source/runtime.c', 'wine-nx-probe/CMakeLists.txt'}, native_delta
    assert feature_delta == {'src/runtime/pes_gameplaytool_control.h'}, feature_delta
    runtime = (a.runtime/'native-source/wine-nx-probe/source/runtime.c').read_text()
    main_body = runtime[runtime.index('int main( int argc, char **argv )'):]
    assert main_body.index('pes_gameplaytool_control(guest_tests, gameplaytool_enabled)') < main_body.index('fx_launcher_start()')
    assert main_body.index('fx_launcher_start()') < main_body.index('[LW4-KITCONTROL] Gameplaytool=')
    nro_blob = (a.runtime/'pes13-fex.nro').read_bytes()
    for marker in (b'0.3.9-lw4', b'[LW4-KITCONTROL] Gameplaytool=', b'gameplaytool,*gameplaytool='):
        assert marker in nro_blob, marker
    # Reuse unchanged sanitizer evidence only after verifying the exact inputs.
    host = read(a.previous/'evidence/host-tests.json')
    assert host['passed']
    for rel, digest in host['sources'].items(): assert sha(ROOT/rel) == digest, rel
    original, altered, loading = prepare(a.game)
    a.output.mkdir(parents=True)

    def put(rel, data):
        p = a.output/rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def copy(p, rel): put(rel, p.read_bytes())
    def jsonfile(rel, obj): put(rel, (json.dumps(obj, indent=2)+'\n').encode())

    copy(a.runtime/'pes13-fex.nro', NRO)
    copy(a.previous/NRO, 'rollback/'+NRO)
    put('loading-control/'+CONFIG, altered)
    put('loading-rollback/'+CONFIG, original)
    jsonfile('evidence/loading-control.json', loading)
    for name in ('build.json', 'prepared.json'): copy(a.runtime/name, 'evidence/'+name)
    for name in ('binary-tests.json', 'policy-tests.json', 'compression-audit.json', 'analysis.json'):
        copy(a.evidence/name, 'evidence/'+name)
    copy(a.previous/'evidence/host-tests.json', 'evidence/unchanged-host-tests.json')
    copy(a.previous/'package.json', 'evidence/lw3-package.json')
    for directory in ('source', 'licenses'):
        if (a.previous/directory).exists():
            shutil.copytree(a.previous/directory, a.output/directory/'lw3-baseline')
    sources = set(build['inputs']) | {
        'tools/package-pes-low-window-kitcontrol.py', 'tools/kitserver_loading_control.py',
        'tools/analyze-pes-low-window-run.py', 'tools/analyze-pes-kitserver-control.py',
        'tools/audit-pes-kitserver-calls.py',
        'tests/pes_low_window_binary.py', 'tests/pes_gameplaytool_binary.py'}
    for rel in sorted(sources): copy(ROOT/rel, 'source/lw4/'+rel)
    diff = []
    for root, names in (('native-source', native_delta), ('feature', feature_delta)):
        for rel in sorted(names):
            before, after = a.previous_runtime/root/rel, a.runtime/root/rel
            diff.extend(difflib.unified_diff(before.read_text().splitlines(keepends=True) if before.exists() else [],
                after.read_text().splitlines(keepends=True), fromfile='a/'+root+'/'+rel, tofile='b/'+root+'/'+rel))
            copy(after, 'source/generated/'+root+'/'+rel)
    put('source/lw4.patch', ''.join(diff).encode())
    copy(ROOT/'docs/PES13-LOW-WINDOW-V4-KITSERVER-CONTROL.md', 'README.md')
    files = {p.relative_to(a.output).as_posix(): sha(p) for p in sorted(a.output.rglob('*')) if p.is_file()}
    payload = {n:h for n,h in files.items() if n.startswith('switch/')}
    assert payload == {NRO:build['nro_sha256']}
    assert not list(a.output.rglob('*.dll')) and not list(a.output.rglob('*.zip')) and not list(a.output.rglob('*.nsp'))
    jsonfile('package.json', dict(built=True, version=build['version'], abi='fxtmem-v1',
        hardware_tested=False, game_speed_fix_verified=False, loading_gain_verified=False,
        native_elf_sha256=build['elf_sha256'], previous_nro_sha256=old_build['nro_sha256'],
        change='Disable optional Gameplaytool.dll by Wine load policy; kitserver_gameplaytool=1 restores it after restart.',
        optional_loading_control='Separate config overlay omits fserv_3 and fserv_4; do not combine on first comparison.',
        fex_changed=False, clock_scaled=False, dxvk_changed=False, game_assets_changed=False,
        payload=payload, files=files))
    files['package.json'] = sha(a.output/'package.json')
    put('SHA256SUMS.txt', ''.join(f'{h}  {n}\n' for n,h in sorted(files.items())).encode())
    for rel, digest in files.items(): assert sha(a.output/rel) == digest, rel
    # Active PC game files remain exactly as found.
    for rel, digest in loading['input_sha256'].items(): assert sha(a.game/'kitserver13'/rel) == digest, rel
    print(f'LW4 packaged: {len(files)} verified files; main NRO + separate loading control; no ZIP.', flush=True)


if __name__ == '__main__': main()
