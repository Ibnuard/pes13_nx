"""Sanitizer test of shipping frame observer plus native call-site audit."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.build_root / 'fex-experiment/wine3/native-source'
    vulkan = (source / 'dlls/win32u/vulkan.c').read_text()
    begin = vulkan.index('static VkResult win32u_vkQueuePresentKHR(')
    end = vulkan.index('\nstatic LARGE_INTEGER *get_nt_timeout', begin)
    body = vulkan[begin:end]
    assert body.count('return res;') == 1 and body.count('return ') == 1
    assert body.count('wine_nx_fex_frame_note(') == 1
    assert body.count('res = device->p_vkQueuePresentKHR(') == 1
    assert body.index('pthread_mutex_lock( &lock );') < body.index('    fex_host = wine_nx_fex_frame_tick();')
    assert body.index('    fex_host_end = wine_nx_fex_frame_tick();') < body.index('pthread_mutex_unlock( &lock );')
    assert body.index('mem_free( &pool );') < body.index('wine_nx_fex_frame_note(')
    runtime = (source / 'wine-nx-probe/source/runtime.c').read_text()
    for name in ('fex_frame_metrics.h', 'fex_frame_runtime.h'):
        assert (root / 'src/runtime' / name).read_text() in runtime
    assert ('if (ticks % 50 == 0) fex_frame_report();' in runtime or
            'if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); }' in runtime)
    assert '"DXVK_CONFIG_FILE=C:\\\\PES13\\\\dxvk.conf\\0"' in runtime
    work = args.build_root / 'fex-experiment/frame-test'
    work.mkdir(exist_ok=True)
    exe = work / 'frame-observer'
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-pthread',
                    str(root / 'tests/fex_frame_native.c'), '-o', str(exe)], check=True)
    result = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    names = ('src/runtime/fex_frame_metrics.h', 'src/runtime/fex_frame_runtime.h',
             'tools/fex_frame_patches.py', 'tests/fex_frame_native.c', 'tests/fex_frame.py')
    report = {'passed': True, 'hardware_tested': False, 'sanitizers': ['address', 'undefined'],
              'scope': __doc__, 'output': result.stdout.strip(),
              'source_sha256': {p: sha((root / p).read_bytes()) for p in names},
              'vulkan_c_sha256': sha(vulkan.encode()), 'runtime_c_sha256': sha(runtime.encode())}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
