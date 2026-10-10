"""Prepare a one-file, reversible test of the failing optional gameplay plugin.

The active game directory is read-only. This does not claim a game-speed fix.
Use the existing LW3 NRO so the comparison changes only one plugin entry.
"""
import argparse
import collections
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

import pefile

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'switch/pes13-fex/drive_c/PES13/kitserver13/plugin.ini'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game', type=Path, required=True)
    ap.add_argument('--log', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.resolve().relative_to((ROOT / 'dist').resolve())
    assert not a.output.exists(), 'Use a fresh output directory'
    original = (a.game / 'kitserver13/plugin.ini').read_bytes()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(original.decode('utf-8-sig'))
    # Stopping at key 2 is specific to the supplied two-plugin configuration.
    # Reject a different list rather than accidentally skipping later plugins.
    assert dict(cfg['plugin']) == {'1': 'camera.dll', '2': 'gameplay.dll'}
    altered, count = re.subn(rb'(?im)^2[ \t]*=[ \t]*gameplay\.dll[ \t]*(?=\r?$)',
                            b'; LW3 control: optional gameplay.dll disabled', original)
    assert count == 1
    check = configparser.ConfigParser(interpolation=None)
    check.read_string(altered.decode('utf-8-sig'))
    assert dict(check['plugin']) == {'1': 'camera.dll'}

    spec = importlib.util.spec_from_file_location('lw_log', ROOT / 'tools/analyze-pes-low-window-run.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw = a.log.read_bytes()
    rows = mod.records(raw.decode(errors='replace'))
    assert any('[STARTUP] FEXTendo 0.3.9-lw3' in s for _, s in rows)
    live = []
    clocks = []
    for t, s in rows:
        fields = dict(re.findall(r'([a-zA-Z_]+)=([\w.-]+)', s))
        if s.startswith('[LW3-LIVESET] layout='):
            live.append(dict(seconds=t, **fields))
        elif s.startswith('[LW3-CLOCKSITE] layout='):
            clocks.append(dict(seconds=t, **fields))
    assert live and clocks

    kernel_path = a.game.parent / 'windows/syswow64/kernel32.dll'
    kernel_raw = kernel_path.read_bytes()
    kernel = pefile.PE(data=kernel_raw)
    exports = {symbol.name.decode(): kernel.OPTIONAL_HEADER.ImageBase + symbol.address
               for symbol in kernel.DIRECTORY_ENTRY_EXPORT.symbols
               if symbol.name in (b'QueryPerformanceCounter', b'QueryPerformanceFrequency')}
    expected = {'QPF': exports['QueryPerformanceFrequency'], 'QPC-candidate': exports['QueryPerformanceCounter']}
    clock_matches = all(c.get('kind') == 'indirect' and
                        int(c['target'], 16) == expected.get(c['role']) for c in clocks)

    inputs = {str(p.resolve()): sha(p.read_bytes()) for p in (
        a.game / 'kitserver13/plugin.ini', a.game / 'kitserver13/config.txt',
        a.game / 'kitserver13/gameplaytool.ini', a.game / 'kitserver13/plugin/gameplay.ini',
        a.game / 'kitserver13/Gameplaytool.dll', a.game / 'kitserver13/plugin/gameplay.dll',
        a.game / 'kitserver13/speeder.dll', kernel_path)}
    report = dict(
        input_log_sha256=sha(raw), duration_s=rows[-1][0],
        live_samples=len(live), first_live_s=live[0]['seconds'], last_live_s=live[-1]['seconds'],
        live_flags=dict(collections.Counter(d['flags'] for d in live)),
        live_frame_skip=dict(collections.Counter(d['frame_skip'] for d in live)),
        live_crc_valid=dict(collections.Counter(d['crc_valid'] for d in live)),
        clock_samples=len(clocks), clock_targets_match_local_kernel32_exports=clock_matches,
        kernel32_exports={k: f'{v:08x}' for k, v in exports.items()},
        gameplay_failures=[dict(seconds=t, text=s) for t, s in rows
                           if 'gameplay.dll' in s and ('failed' in s or 'status=c0000005' in s)],
        local_inputs_sha256=inputs,
        user_observation='Kickoff after approximately three minutes; match clock, players and ball feel accelerated.',
        conclusion='The sampled loaded WECF flag stays off and the observed standard Speeder QPF hook is absent. '
                   'The optional gameplay plugin fails attach. Causality for accelerated simulation remains unproven.',
        limitations=['Five-second snapshots do not capture every transient or the engine timing-object copy.',
                     'Export targets do not measure returned clock values or exclude hooks elsewhere.',
                     'A failed DllMain is not proof that no earlier guest-memory writes occurred.',
                     'Present counts are not unique simulation frames or a measured game-speed multiplier.'])
    a.output.mkdir(parents=True)

    def put(rel, data):
        p = a.output / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    put(TARGET, altered)
    put('rollback/' + TARGET, original)
    put('evidence/analysis.json', (json.dumps(report, indent=2) + '\n').encode())
    put('source/package-pes-kitserver-gameplay-control.py', Path(__file__).read_bytes())
    put('source/analyze-pes-low-window-run.py', (ROOT / 'tools/analyze-pes-low-window-run.py').read_bytes())
    put('README.md', (ROOT / 'docs/PES13-LW3-GAMEPLAY-CONTROL.md').read_bytes())
    files = {p.relative_to(a.output).as_posix(): sha(p.read_bytes())
             for p in sorted(a.output.rglob('*')) if p.is_file()}
    assert {n for n in files if n.startswith('switch/')} == {TARGET}
    assert not any(a.output.rglob('*.dll')) and not any(a.output.rglob('*.nro'))
    manifest = dict(kind='config-only A/B control', nro='existing 0.3.9-lw3; unchanged',
                    hardware_tested=False, game_speed_fix_verified=False,
                    change='Only remove plugin key 2=gameplay.dll; camera key 1 retained.',
                    payload={TARGET: sha(altered)}, rollback_sha256=sha(original), files=files)
    put('package.json', (json.dumps(manifest, indent=2) + '\n').encode())
    files['package.json'] = sha((a.output / 'package.json').read_bytes())
    put('SHA256SUMS.txt', ''.join(f'{h}  {n}\n' for n, h in sorted(files.items())).encode())
    for p, digest in inputs.items():
        assert sha(Path(p).read_bytes()) == digest, 'Source changed: ' + p
    for rel, digest in files.items():
        assert sha((a.output / rel).read_bytes()) == digest, rel
    print(json.dumps({k: report[k] for k in ('live_samples', 'live_frame_skip', 'clock_samples',
        'clock_targets_match_local_kernel32_exports', 'gameplay_failures')}, indent=2))
    print('Ready: one plugin.ini overlay, exact original rollback; source game files untouched; no new NRO/ZIP.')


if __name__ == '__main__':
    main()
