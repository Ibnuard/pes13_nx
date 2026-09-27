#!/usr/bin/env python3
"""Read-only generated-source regression; scratch output, real host pthreads.

python3 tests/fex_resume_gate.py --source /path/to/native-source --mode red
python3 tests/fex_resume_gate.py --source /path/to/native-source
RED must compile, execute and fail specifically on irrelevant shared wakeups.
No generated input is written; libnx condvarWaitTimeout is a modeled seam.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'tools'))


def function(text, name):
    match = re.search(r'^static [^;\n]*\b' + re.escape(name) + r'\s*\(', text, re.M)
    if not match:
        match = re.search(r'^void ' + re.escape(name) + r'\s*\(', text, re.M)
    if not match:
        raise AssertionError('missing function ' + name)
    start = match.start()
    brace = text.index('{', match.end())
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def run_native(source, threads, root, label, sanitize=False):
    out = root / label
    out.mkdir()
    (out / 'horizon_threads.h').write_text(threads)
    sync = (PROJECT / 'src/runtime/fex_sync_horizon.h').read_text()
    wait_slice = re.search(r'^#define HORIZON_SERVER_WAIT_SLICE[^\n]+', source, re.M)
    assert wait_slice, 'generated wait slice missing'
    slices = [wait_slice.group()]
    # Read original router helper, not a replacement event broadcast model.
    for name in ('fex_sync_signal_object_locked', 'horizon_server_signal_changed_locked'):
        slices.append(function(sync, name))
    slices.append(function(source, 'horizon_server_sleep_locked'))
    gate = re.search(r'    pthread_mutex_lock\( &horizon_server_objects_mutex \);\n'
                     r'    while \(connection->thread && !horizon_thread_may_start[^\n]+\n'
                     r'        horizon_server_sleep_locked[^\n]+\n'
                     r'    if \(connection->thread\)[^\n]+\n'
                     r'    pthread_mutex_unlock\( &horizon_server_objects_mutex \);', source)
    assert gate, 'generated start gate missing'
    slices.append('static void real_start_gate(struct horizon_server_connection *connection)\n{\n'
                  + gate.group() + '\n}')
    if '/* FEX3_RESUME_GATE_BEGIN */' in source:
        slices.append('#define FEX_RESUME_TEST 1')
        a = source.index('/* FEX3_RESUME_GATE_BEGIN */')
        b = source.index('/* FEX3_RESUME_GATE_END */', a)
        slices.append(source[a:b])
    slices.append(function(source, 'horizon_server_end_thread_locked'))
    slices.append(function(source, 'horizon_server_handle_resume_thread'))
    begin = source.index('static unsigned int fex_thread_begin_suspend(')
    end = source.index('static int horizon_server_handle_terminate_thread(', begin)
    slices.append(source[begin:end])
    (out / 'handlers.inc').write_text('\n\n'.join(slices))
    binary = out / 'native'
    cmd = [os.environ.get('CC', 'cc'), '-std=c11', '-O1', '-g', '-Wall', '-Wextra',
           '-Werror', '-Wno-unused-function', '-pthread', '-I', str(out),
           str(PROJECT / 'tests/fex_resume_gate_native.c'), '-o', str(binary)]
    if sanitize:
        cmd += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    print('COMPILE', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True, timeout=60)
    # Apple ASan supports address/UB checks, not LeakSanitizer.
    leaks = 0 if sys.platform == 'darwin' else 1
    env = dict(os.environ, ASAN_OPTIONS=f'detect_leaks={leaks}:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    result = subprocess.run([str(binary)], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=60, env=env)
    print(result.stdout, end='', flush=True)
    print(label, 'exit=', result.returncode, flush=True)
    return result


def patch_checks(module, before, after):
    horizon, runtime = module.HORIZON, module.RUNTIME
    assert {k for k in before if before[k] != after[k]} == {horizon, runtime}
    stripped = after[horizon]
    a = stripped.index('\n\n' + module.BEGIN)
    b = stripped.index(module.END, a) + len(module.END)
    stripped = stripped[:a] + stripped[b:]
    for name in ('horizon_server_handle_resume_thread', 'horizon_server_end_thread_locked',
                 'horizon_server_handle_suspend_thread'):
        stripped = stripped.replace(function(stripped, name), function(before[horizon], name))
    assert stripped == before[horizon], 'unrelated source changed'

    # Every rejection must precede every write, including late runtime drift.
    cases = [('idempotence', dict(after))]
    for name in ('horizon_server_handle_resume_thread', 'horizon_server_end_thread_locked',
                 'horizon_server_sleep_locked', 'horizon_server_handle_suspend_thread'):
        case = dict(before)
        span = function(case[horizon], name)
        case[horizon] = case[horizon].replace(span, span.replace('{', '{ /* drift */', 1))
        cases.append((name, case))
    case = dict(before)
    case[horizon] = case[horizon].replace('#define HORIZON_SERVER_WAIT_SLICE    200000LL',
                                         '#define HORIZON_SERVER_WAIT_SLICE    100000LL')
    cases.append(('20ms constant drift', case))
    header = 'dlls/ntdll/unix/horizon_threads.h'
    case = dict(before)
    case[header] = case[header].replace('if (thread->suspend) thread->suspend--;',
                                       'if (thread->suspend) thread->suspend = 0;')
    cases.append(('thread resume helper drift', case))
    for anchor in ('fex_sync_horizon.h',):
        case = dict(before); case[horizon] = case[horizon].replace(anchor, anchor + '.missing')
        cases.append((anchor, case))
    case = dict(before)
    duplicate = function(case[horizon], 'horizon_server_handle_resume_thread')
    case[horizon] += '\n' + duplicate
    cases.append(('duplicate resume function', case))
    for anchor in ('static void *log_flusher( void *arg )',
                   'if (ticks % 50 == 0) fex_sync_report();', '[FEX3-SYNC] startup'):
        case = dict(before); case[runtime] = case[runtime].replace(anchor, anchor + '_drift')
        cases.append((anchor, case))
    for name, case in cases:
        writes = []
        try:
            module.apply(case.__getitem__, lambda *args: writes.append(args), PROJECT)
        except ValueError:
            assert not writes, (name, 'partial write on rejected input')
        else:
            raise AssertionError('accepted source drift/reapplication: ' + name)
    print(f'PASS patch checks: {len(cases)} rejection cases, zero partial writes; unrelated source/ABI unchanged')


def mutation_checks(source, threads, root, sanitize):
    # These intentionally wrong variants must execute and fail semantically;
    # compile failures are never accepted as RED evidence.
    cases = [
        ('NO_TERMINATION_WAKE',
         '    fex_resume_wake_locked(thread, 1);  /* before reference drop; keep broad notification below */',
         '    /* fault injection: missing termination notification */',
         'FAIL termination missing private wake'),
        ('BROAD_RESUME',
         '\n    else ++fex_resume_counts.ignored;',
         '\n    else ++fex_resume_counts.ignored;\n    horizon_server_signal_changed_locked();',
         'broadcasts == before && signals == before_signals'),
        ('WRONG_OBJECT',
         '        if (waiter->object != object) continue;',
         '        if (!object) continue; /* fault: wake every object */',
         'signals == before_signals + 1 && other.thread.self_suspended'),
    ]
    for label, old, new, expected in cases:
        assert source.count(old) == 1, label
        result = run_native(source.replace(old, new), threads, root, label, sanitize)
        assert result.returncode != 0 and expected in result.stdout, result
    print(f'PASS mutation checks: {len(cases)} wrong routing variants compiled and failed expected assertions')


def main():
    if not __debug__:
        raise RuntimeError('Resume-gate host test requires assertions; disable -O/-OO and PYTHONOPTIMIZE')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--mode', choices=('red', 'green', 'both'), default='both')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--mutations', action='store_true', help='compile/run three wrong variants; require semantic RED')
    args = parser.parse_args()
    source_path = args.source / 'dlls/ntdll/unix/horizon.c'
    thread_path = args.source / 'dlls/ntdll/unix/horizon_threads.h'
    source, threads = source_path.read_text(), thread_path.read_text()
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    print('SOURCE', source_path, 'sha256=' + digest, flush=True)
    assert 'fex_sync_horizon.h' in source and 'self_suspended' in threads
    assert 'FEX3_RESUME_GATE_BEGIN' not in source, 'input must be pre-resume-gate baseline'
    temp = os.environ.get('TMPDIR')
    if not temp:
        raise SystemExit('TMPDIR required: use Hermes scratch, not /tmp')
    if Path(temp).resolve() == Path('/tmp').resolve():
        raise SystemExit('TMPDIR=/tmp forbidden: set Hermes scratch explicitly')
    with tempfile.TemporaryDirectory(prefix='fex-resume-', dir=temp) as directory:
        root = Path(directory)
        if args.mode in ('red', 'both'):
            result = run_native(source, threads, root, 'RED', args.sanitize)
            assert result.returncode == 42 and 'FAIL irrelevant self-suspend wake' in result.stdout, result
            assert re.search(r'irrelevant=[1-9][0-9]*', result.stdout), result.stdout
        if args.mode in ('green', 'both'):
            import fex_resume_patches
            runtime = (args.source / 'wine-nx-probe/source/runtime.c').read_text()
            files = {'dlls/ntdll/unix/horizon.c': source,
                     'dlls/ntdll/unix/horizon_threads.h': threads,
                     'wine-nx-probe/source/runtime.c': runtime}
            before = dict(files)
            def replace(name, old, new):
                assert files[name].count(old) == 1, (name, old)
                files[name] = files[name].replace(old, new)
            fex_resume_patches.apply(files.__getitem__, replace, PROJECT)
            assert files['dlls/ntdll/unix/horizon_threads.h'] == threads
            assert '[FEX3-RESUME] isolated self-suspend wake' in files['wine-nx-probe/source/runtime.c']
            assert 'if (ticks % 50 == 0) wine_nx_fex_resume_report();' in files['wine-nx-probe/source/runtime.c']
            patch_checks(fex_resume_patches, before, files)
            result = run_native(files['dlls/ntdll/unix/horizon.c'], threads, root,
                                'GREEN', args.sanitize)
            assert result.returncode == 0 and 'PASS resume-gate' in result.stdout, result
            if args.mutations:
                mutation_checks(files['dlls/ntdll/unix/horizon.c'], threads, root, args.sanitize)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == digest
    assert thread_path.read_text() == threads
    print('PASS input source unchanged; host slices only, no generated-source build')


if __name__ == '__main__':
    main()
