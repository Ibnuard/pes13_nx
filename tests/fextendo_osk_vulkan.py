"""Exercise the actual Vulkan OSK code under ASan/UBSan with a strict API model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--include', type=Path, default=Path('/home/blekjek/pes13-build/mesa-vulkan/install/opt/devkitpro/portlibs/switch/include'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix='fextendo-osk-vk-') as temp:
        binary = Path(temp)/'test'
        subprocess.run(['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-misleading-indentation', '-fsanitize=address,undefined',
                        '-I'+str(a.include), str(ROOT/'tests/fextendo_osk_vulkan.c'), '-o', str(binary)], check=True)
        r = subprocess.run([str(binary)], text=True, capture_output=True)
        assert r.returncode == 0 and not r.stderr, (r.stdout, r.stderr)
    sources = ['tests/fextendo_osk_vulkan.py', 'tests/fextendo_osk_vulkan.c',
               'src/runtime/fextendo_osk_vulkan.h', 'src/runtime/fextendo_osk_frame.h', 'tools/fextendo_osk_patches.py']
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({'passed': True, 'hardware_tested': False, 'result': r.stdout.strip(),
        'sources': {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources},
        'limits': 'Real overlay C with Vulkan API model, not physical GPU or Switch validation.'}, indent=2)+'\n')
    print(r.stdout.strip())


if __name__ == '__main__':
    main()
