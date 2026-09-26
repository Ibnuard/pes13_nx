"""Test read-only game timing and per-thread batching with ASan/UBSan."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.build_root / 'fex-experiment/wine3/native-source'
    runtime = (source / 'wine-nx-probe/source/runtime.c').read_text()
    virtual = (source / 'dlls/ntdll/unix/virtual.c').read_text()
    for name in ('fex_game_timing.h', 'fex_game_timing_runtime.h', 'fex_log_policy.h'):
        assert (root / 'src/runtime' / name).read_text() in runtime
    assert 'if (ticks % 25 == 0) fex_game_timing_report();' in runtime
    assert 'fex_game_timing_enabled = !guest_tests &&' in runtime
    assert 'fex_log_should_flush(line, log_flusher_running, log_line_is_urgent(line))' in runtime
    start = runtime.index('static void *log_flusher( void *arg )')
    end = runtime.index('\n}', start)
    loop = runtime[start:end]
    assert loop.count('fex_log_metrics_batch = 1;') == 1
    assert loop.count('fex_log_metrics_batch = 0;') == 1
    assert loop.index('fex_log_metrics_batch = 1;') < loop.index('runtime_report_interpreter();')
    assert loop.index('fex_game_timing_report();') < loop.index('fex_log_metrics_batch = 0;')
    assert loop.count('fflush( log_file );') == 1  # commit entire 5s batch once
    assert loop.index('fex_log_metrics_batch = 0;') < loop.index('fflush( log_file );')
    reader = virtual.split('int wine_nx_fex_timing_read(', 1)[1].split('\n}', 1)[0]
    assert 'virtual_uninterrupted_read_memory(' in reader
    assert 'size > 4096 || size > UINT32_MAX - address' in reader
    assert '__TRY' not in reader and 'NtReadVirtualMemory' not in reader
    helper = virtual.split('SIZE_T virtual_uninterrupted_read_memory(', 1)[1].split('\n}', 1)[0]
    assert 'server_enter_uninterrupted_section( &virtual_mutex' in helper
    assert 'get_unix_prot( get_host_page_vprot( addr )) & PROT_READ' in helper
    for p in ('dlls/ntdll/unix/sync.c', 'dlls/win32u/vulkan.c'):
        assert 'fex_game_snapshot' not in (source / p).read_text()  # no hot-path probe
    work = args.build_root / 'fex-experiment/game-timing-test'
    work.mkdir(exist_ok=True)
    exe = work / 'game-timing'
    subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-pthread',str(root/'tests/fex_game_timing_native.c'),
                    '-o',str(exe)],check=True)
    result = subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=30)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    paths = ('src/runtime/fex_game_timing.h','src/runtime/fex_game_timing_runtime.h',
             'src/runtime/fex_log_policy.h','tools/fex_game_timing_patches.py',
             'tests/fex_game_timing_native.c','tests/fex_game_timing.py')
    report = {'passed':True,'hardware_tested':False,'scope':__doc__,
              'sanitizers':['address','undefined'],'output':result.stdout.strip(),
              'source_sha256':{p:sha(root/p) for p in paths},
              'patched_source_sha256':{p:sha(source/p) for p in
                ('wine-nx-probe/source/runtime.c','dlls/ntdll/unix/virtual.c')}}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
