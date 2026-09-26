"""Validate passive pipeline instrumentation against original native call sites."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def driver_calls(text):
    # The observer may surround these calls but cannot change any argument,
    # result assignment, or timeout. Compare all native driver calls, not only
    # instrumented ones, against the immutable pre-FEX snapshot.
    return re.findall(r'\b(?:res|params->result)\s*=\s*[^;\n]*p_vk(?:AcquireNextImage\w*|QueueSubmit\w*|WaitForFences|WaitSemaphores\w*)\([^;]*;', text)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-root', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = args.build_root / 'fex-experiment/wine3'
    hashes = {}
    sha = lambda b: hashlib.sha256(b).hexdigest()
    for name, count in (('dlls/win32u/vulkan.c', 4), ('dlls/winevulkan/vulkan_thunks.c', 6)):
        original = (work / 'native-source-originals' / name).read_text()
        data = (work / 'native-source' / name).read_text()
        assert driver_calls(data) == driver_calls(original), name
        assert data.count('wine_nx_fex_pipeline_note(') == count + 1, name
        assert data.count('uint64_t fex_stage_begin = wine_nx_fex_frame_tick();') == count, name
        if name.endswith('vulkan_thunks.c'):
            assert 'extern void wine_nx_fex_pipeline_note(unsigned, uint64_t, int);\n\n#ifdef _WIN64\nstatic NTSTATUS thunk64_vkWaitForFences' in data
        hashes[name] = sha(data.encode())
    name = 'dlls/ntdll/unix/virtual.c'
    data = (work / 'native-source' / name).read_text()
    assert data.count('wine_nx_fex_shared_clock_note(interrupt_time);') == 1
    assert '__atomic_store_n( &data->TickCountQuad, tick_count, __ATOMIC_RELEASE );\n    wine_nx_fex_shared_clock_note(interrupt_time);' in data
    hashes[name] = sha(data.encode())
    name = 'wine-nx-probe/source/runtime.c'
    data = (work / 'native-source' / name).read_text()
    assert (root / 'src/runtime/fex_pipeline_runtime.h').read_text() in data
    assert 'if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); }' in data
    hashes[name] = sha(data.encode())
    build = args.build_root / 'fex-experiment/pipeline-test'
    build.mkdir(exist_ok=True)
    exe = build / 'pipeline-observer'
    subprocess.run(['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(root / 'tests/fex_pipeline_native.c'),
                    '-o', str(exe)], check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=30)
    names = ('tests/fex_pipeline.py', 'tests/fex_pipeline_native.c',
             'src/runtime/fex_pipeline_runtime.h', 'src/runtime/fex_frame_metrics.h',
             'tools/fex_pipeline_patches.py')
    report = {'passed': True, 'hardware_tested': False, 'sanitizers': ['address', 'undefined'],
              'output': result.stdout.strip(), 'patched_source_sha256': hashes,
              'source_sha256': {name: sha((root / name).read_bytes()) for name in names}}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
