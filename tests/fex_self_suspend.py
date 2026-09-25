"""Exercise shipping suspend/resume handlers with real concurrent pthread waits."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = a.build_root / 'fex-experiment/wine3/native-source/dlls/ntdll/unix'
    work = a.build_root / 'fex-experiment/self-suspend-test'
    work.mkdir(exist_ok=True)
    text = (source / 'horizon.c').read_text()
    first = text.index('static int horizon_server_handle_resume_thread(')
    last = text.index('static int horizon_server_handle_terminate_thread(', first)
    handlers = text[first:last]
    assert (root / 'src/runtime/fex_self_suspend.h').read_text() in handlers
    (work / 'fex_self_suspend_handlers.inc').write_text(handlers)
    exe = work / 'self-suspend'
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-pthread',
                    '-I' + str(source), '-I' + str(work),
                    str(root / 'tests/fex_self_suspend_native.c'), '-o', str(exe)], check=True)
    result = subprocess.run([str(exe)], check=True, timeout=65, capture_output=True, text=True)
    assert 'PASS self-suspend:' in result.stdout
    names = ('src/runtime/fex_self_suspend.h', 'src/runtime/fex_suspend_observe.h',
             'tools/fex_self_suspend_patches.py', 'tests/fex_self_suspend_native.c',
             'tests/fex_self_suspend.py')
    sha = lambda data: hashlib.sha256(data).hexdigest()
    report = {'passed': True, 'scope': 'Actual server handlers and thread state with real pthread waits; transport modeled',
              'hardware_tested': False, 'sanitizers': ['address', 'undefined'],
              'source_sha256': {name: sha((root / name).read_bytes()) for name in names},
              'horizon_threads_sha256': sha((source / 'horizon_threads.h').read_bytes()),
              'horizon_c_sha256': sha((source / 'horizon.c').read_bytes()),
              'output': result.stdout.strip()}
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
