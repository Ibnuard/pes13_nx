"""Sanitize settings aliases and the real four-preset transaction writer."""
import argparse, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); checks = []
    with tempfile.TemporaryDirectory(prefix='pes-settings-') as tmp:
        tmp = Path(tmp); game = tmp/'game'
        shutil.copytree(ROOT/'config/fextendo/presets', game/'launcher/presets')
        for name in ('pes_settings_route', 'fextendo_preset_failures'):
            exe = tmp/name
            subprocess.run(['gcc', '-std=c11', '-O1', '-g', '-D_POSIX_C_SOURCE=200809L',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            str(ROOT/f'tests/{name}.c'), '-o', str(exe)], check=True)
            command = [str(exe)] + ([str(game)] if name == 'fextendo_preset_failures' else [])
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode: print(result.stdout, result.stderr, flush=True)
            result.check_returncode(); checks.append(result.stdout.strip())
            print(result.stdout.strip(), flush=True)
    files = ('src/runtime/pes_settings_route.h', 'src/runtime/fextendo_presets.h',
             'tests/pes_settings_route.c', 'tests/fextendo_preset_failures.c', 'tests/pes_settings_host.py')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(dict(passed=True, hardware_tested=False, checks=checks,
        sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}), indent=2)+'\n')


if __name__ == '__main__': main()
