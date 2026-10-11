"""Run the OSK's display function and renderer and frame publisher."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='fextendo-osk-surface-') as temp:
        binary = Path(temp)/'test'
        subprocess.run(['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-function', '-Wno-missing-field-initializers', '-Wno-misleading-indentation',
            '-fsanitize=address,undefined', '-pthread', str(ROOT/'tests/fextendo_osk_surface.c'), '-lm', '-o', str(binary)], check=True)
        result = subprocess.run([str(binary), str(a.assets.resolve())], capture_output=True, text=True)
        assert result.returncode == 0 and not result.stderr, (result.stdout, result.stderr)
    sources = ['tests/fextendo_osk_surface.py', 'tests/fextendo_osk_surface.c',
        'src/runtime/fextendo_osk_display.h', 'src/runtime/fextendo_osk_frame.h', 'src/runtime/fextendo_osk_ui.h',
        'src/runtime/fextendo_ui.h', 'src/runtime/fextendo_osk.h']
    report = {'passed': True, 'hardware_tested': False, 'result': result.stdout.strip(),
        'sources': {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources},
        'font_sha256': hashlib.sha256((a.assets/'launcher/font.bin').read_bytes()).hexdigest(),
        'limits': 'Real C pixel publisher and rendering under ASan/UBSan. Tick/touch modeled; GPU/display verified separately; on-device visibility not verified.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(result.stdout.strip())


if __name__ == '__main__':
    main()
