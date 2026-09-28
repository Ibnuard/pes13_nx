#!/usr/bin/env python3
"""Offline regressions for real pinned Horizon source slices, not hardware tests.

Default: patch the retained pinned slices, compile, run with ASan/UBSan.
--source PATH: use horizon.c or a Wine source root instead of retained slices.
--unpatched/--already-patched: run supplied source as-is (pin must fail).
CC may select a host compiler; no Switch SDK, build, install or network needed.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 'dlls/ntdll/unix/horizon.c'
SCENARIOS = ('normal', 'rearm-poll', 'cancel-poll', 'relative-overflow', 'periodic-overflow', 'periodic-catchup')


def function(source, name):
    match = re.search(r'^static [^\n]*\b' + re.escape(name) +
                      r'\([^;{]*?\)\s*\n\{', source, re.M)
    if not match:
        raise AssertionError('Missing source function: ' + name)
    end, depth = match.end(), 1
    while depth and end < len(source):
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    assert not depth, 'Unclosed source function: ' + name
    return source[match.start():end] + '\n'


def patch_module():
    path = ROOT / 'tools/fex_runtime_fixes.py'
    spec = importlib.util.spec_from_file_location('fex_runtime_fixes_patch', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patched(source):
    module = patch_module()
    data = {HORIZON: source}

    def read(name):
        return data[name]

    def replace(name, old, new, count=1):
        if data[name].count(old) != count:
            raise AssertionError('Replacement anchor mismatch: ' + name)
        data[name] = data[name].replace(old, new)

    module.apply(read, replace, ROOT)
    return data[HORIZON]


def timer_code(source):
    names = ('horizon_server_handle_polls_locked',
             'horizon_server_handle_set_timer',
             'horizon_server_handle_cancel_timer',
             'horizon_server_handle_get_timer_info',
             'horizon_server_wait_object_locked',
             'horizon_server_select_wait',
             'horizon_server_select_signal_and_wait',
             'horizon_server_select_status',
             'horizon_server_select_polls_locked',
             'horizon_server_handle_select')
    if 'static void horizon_server_update_timers_locked(' in source:
        update = function(source, 'horizon_server_update_timers_locked')
    else:
        # Pin has no expiry pass. Stub only this absent function so RED reaches
        # real set_timer behavior, rather than failing compilation.
        update = 'static void horizon_server_update_timers_locked(void) {}\n'
    # Real TIMER/EVENT switch arms; unrelated object types are not exercised.
    arms = ''
    for original, wrapper, const in (
            ('horizon_server_object_is_signaled', 'horizon_server_object_is_signaled', 'const '),
            ('horizon_server_consume_signal', 'horizon_server_consume_signal', '')):
        body = function(source, original)
        arm = ''
        for kind in ('EVENT', 'TIMER'):
            start = body.index('    case HORIZON_SERVER_OBJECT_' + kind + ':')
            end = body.index('    case ', start + 5)
            arm += body[start:end]
        arms += ('static int ' + wrapper + '(' + const +
                 'struct horizon_server_object *object)\n{\n'
                 '    switch (object->type) {\n' + arm +
                 '    default: break;\n    }\n    return 0;\n}\n')
    sync = 'fex_sync_select_sleep_locked(' in function(source, 'horizon_server_handle_select')
    preamble = ('#define FEX_RUNTIME_FIXES_SYNC 1\n#include "fex_sync_horizon.h"\n' if sync else
                'static void horizon_server_signal_changed_locked(void) {}\n')
    return (preamble + function(source, 'horizon_server_sleep_locked') + arms + update +
            '\n'.join(function(source, name) for name in names))


def compile_run(source, suite, scenario='all', check=True):
    with tempfile.TemporaryDirectory(prefix='fex_runtime_fixes_') as tmp:
        work = Path(tmp)
        code = (timer_code(source) if suite == 'timers' else
                function(source, 'lowest_set_core') +
                function(source, 'horizon_server_follow_client'))
        (work / 'fex_runtime_fixes_source.inc').write_text(code)
        exe = work / suite
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer',
            '-I' + str(work), '-I' + str(ROOT / 'src/runtime'), str(ROOT / 'tests' /
                                ('fex_runtime_fixes_timer.c' if suite == 'timers'
                                 else 'fex_runtime_fixes_affinity.c')),
            '-o', str(exe)]
        build = subprocess.run(command, text=True, capture_output=True, timeout=60)
        report = {'suite': suite, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                  'slice_sha256': hashlib.sha256(code.encode()).hexdigest(),
                  'compile_command': command, 'compile_returncode': build.returncode,
                  'compile_stdout': build.stdout, 'compile_stderr': build.stderr, 'runs': []}
        if not build.returncode:
            cases = SCENARIOS if suite == 'timers' and scenario == 'all' else (
                'normal' if suite == 'affinity' else scenario,)
            for case in cases:
                try:
                    result = subprocess.run([str(exe), case], text=True, capture_output=True, timeout=5)
                    run = {'scenario': case, 'returncode': result.returncode,
                           'stdout': result.stdout, 'stderr': result.stderr, 'timed_out': False}
                except subprocess.TimeoutExpired:
                    run = {'scenario': case, 'returncode': None, 'stdout': '',
                           'stderr': 'Timed out after 5 seconds', 'timed_out': True}
                report['runs'].append(run)
        report['passed'] = (build.returncode == 0 and not build.stderr and bool(report['runs']) and
                            all(r['returncode'] == 0 and not r['stderr'] for r in report['runs']))
        if check:
            print(build.stdout + build.stderr, end='')
            for run in report['runs']:
                print(run['stdout'] + run['stderr'], end='')
            assert report['passed'], f'{suite}: source-slice regression failed'
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--unpatched', '--already-patched', action='store_true',
                        help='Test provided source as-is; never reapply generator')
    parser.add_argument('--only', choices=('timers', 'affinity', 'all'), default='all')
    parser.add_argument('--scenario', default='all', choices=('all',) + SCENARIOS)
    args = parser.parse_args()
    path = args.source or ROOT / 'tests/fex_runtime_fixes_pinned.c'
    if path.is_dir():
        path /= HORIZON
    source = path.read_text()
    print(f'Source: {path}', flush=True)
    generated = source if args.unpatched else patched(source)
    for suite in ('timers', 'affinity') if args.only == 'all' else (args.only,):
        compile_run(generated, suite, args.scenario)
    print(json.dumps({'passed': True, 'suite': args.only,
                      'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                      'generated_sha256': hashlib.sha256(generated.encode()).hexdigest(),
                      'mode': 'as-is' if args.unpatched else 'generated patch',
                      'hardware_tested': False}))


if __name__ == '__main__':
    main()
