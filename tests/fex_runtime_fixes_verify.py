#!/usr/bin/env python3
"""Read-only full-source integration + retained-fixture ASan/UBSan red/green audit.

Writes only --output and disposable TMPDIR host binaries. No prepared source,
master patcher, build configuration or shipping binary is modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

import fex_runtime_fixes as tests

ROOT = tests.ROOT
HORIZON = tests.HORIZON
PROVENANCE = ROOT / 'tests/fex_runtime_fixes_provenance.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_file(path):
    return path / HORIZON if path.is_dir() else path


def upstream_timer(source):
    """Apply retained exact upstream hunks independently of generator's edits."""
    patch = (ROOT / 'tests/fex_runtime_fixes_upstream.patch').read_text()
    hunks = re.split(r'^@@[^\n]*\n', patch, flags=re.M)[1:]
    scopes = (None, None, 'horizon_server_handle_set_timer',
              'horizon_server_handle_cancel_timer', 'horizon_server_handle_get_timer_info',
              'horizon_server_handle_polls_locked', 'horizon_server_handle_select')
    assert len(hunks) == len(scopes)
    for hunk, scope in zip(hunks, scopes):
        lines = hunk.splitlines(keepends=True)
        before = ''.join(line[1:] for line in lines if line.startswith((' ', '-')))
        after = ''.join(line[1:] for line in lines if line.startswith((' ', '+')))
        if scope:
            # Some hunks end in the following function's comment. Apply changed
            # region plus in-function context, without depending on neighbours.
            while before.endswith('\n') and not tests.function(source, scope).count(before):
                assert lines[-1].startswith(' '), 'Missing non-context hunk'
                lines.pop()
                before = ''.join(line[1:] for line in lines if line.startswith((' ', '-')))
                after = ''.join(line[1:] for line in lines if line.startswith((' ', '+')))
            body = tests.function(source, scope)
            assert body.count(before) == 1, scope
            source = source.replace(body, body.replace(before, after, 1), 1)
        else:
            assert source.count(before) == 1
            source = source.replace(before, after, 1)
    return source


def verify_provenance(source):
    manifest = json.loads(PROVENANCE.read_text())
    fixture = (PROVENANCE.parent / manifest['slice_file']).read_bytes()
    upstream = (PROVENANCE.parent / manifest['timer_patch_file']).read_bytes()
    assert digest(source.encode()) == manifest['source_sha256'], 'Not exact pinned horizon.c'
    assert digest(fixture) == manifest['slice_sha256'], 'Retained slice hash mismatch'
    assert digest(upstream) == manifest['timer_patch_sha256'], 'Upstream patch hash mismatch'
    lines = source.splitlines(keepends=True)
    for item in manifest['slices']:
        body = tests.function(source, item['name'])
        assert body == ''.join(lines[item['first_line'] - 1:item['last_line']]), item
        assert tests.function(fixture.decode(), item['name']) == body, item
    return {'pin': manifest['pin'], 'source_sha256': manifest['source_sha256'],
            'retained_slices_verified': len(manifest['slices']),
            'slice_sha256': digest(fixture), 'upstream_patch_sha256': digest(upstream)}


def verify_scope(original, generated):
    allowed = {'horizon_server_handle_set_timer', 'horizon_server_handle_cancel_timer',
               'horizon_server_handle_get_timer_info', 'horizon_server_handle_polls_locked',
               'horizon_server_handle_select', 'horizon_server_follow_client'}
    names = re.findall(r'^static [^\n]*?\b(\w+)\([^;{]*?\)\s*\n\{', original, re.M)
    checked = []
    for name in names:
        if name not in allowed:
            assert tests.function(original, name) == tests.function(generated, name), name
            checked.append(name)
    # All code outside the six edited functions and the timer helper/global must
    # remain byte-for-byte identical, including inline self-suspend support.
    outside_old, outside_new = original, generated
    for name in allowed:
        outside_old = outside_old.replace(tests.function(original, name), '', 1)
        outside_new = outside_new.replace(tests.function(generated, name), '', 1)
    module = tests.patch_module()
    for scope, before, after in module.TIMER_EDITS[:2]:
        assert scope is None
        after = after.replace(tests.function(upstream_timer(original), 'horizon_server_update_timers_locked'),
                              tests.function(generated, 'horizon_server_update_timers_locked'))
        assert outside_new.count(after) == 1
        outside_new = outside_new.replace(after, before, 1)
    assert outside_old == outside_new, 'Unexpected non-timer/affinity source edit'
    return checked


def verify_fail_closed(source):
    module = tests.patch_module()
    late_anchor = '    connection->core_mask = mask;\n'
    bad = source.replace(late_anchor, '    connection->core_mask = 42;\n', 1)
    duplicate = source + '\nstatic struct horizon_server_handle_entry *horizon_server_handles;\n'
    results = []
    for label, candidate in (('reapply', tests.patched(source)), ('late_drift', bad),
                             ('duplicate_anchor', duplicate), ('missing_source', '')):
        writes = []
        try:
            module.apply(lambda name: candidate, lambda *args: writes.append(args), ROOT)
        except RuntimeError as error:
            assert not writes, 'Partial write on rejected source'
            results.append({'case': label, 'error': str(error), 'writes': len(writes)})
        else:
            raise AssertionError('Accepted ' + label)
    writes = []
    module.apply(lambda name: source, lambda *args: writes.append(args), ROOT)
    assert len(writes) == 1 and writes[0][0] == HORIZON and writes[0][1] == source
    return results


def sync_horizon_only(source):
    """Real sibling module; stop at its first write outside horizon.c."""
    sys.path.insert(0, str(ROOT / 'tools'))
    try:
        import fex_sync_patches
    finally:
        sys.path.pop(0)
    data = {HORIZON: source}

    class EndHorizon(Exception):
        pass

    def read(name):
        if name != HORIZON:
            raise EndHorizon()
        return data[name]

    def replace(name, before, after):
        current = read(name)
        assert current.count(before) == 1
        data[name] = current.replace(before, after, 1)

    try:
        fex_sync_patches.apply(read, replace, ROOT)
    except EndHorizon:
        pass
    else:
        raise AssertionError('Expected sibling to reach next file')
    return data[HORIZON]


def verify_composition(source):
    a = tests.patched(sync_horizon_only(source))
    b = sync_horizon_only(tests.patched(source))
    assert a == b, 'Sibling patch ordering changes generated horizon.c'
    assert tests.function(a, 'horizon_server_handle_select').count('pes27_decode(') == 1
    return a


def self_suspend(native_path, generated):
    """Existing real pthread harness, generated from in-memory patched source."""
    expected = (ROOT / 'src/runtime/fex_self_suspend.h').read_text()
    start = generated.index('static int horizon_server_handle_resume_thread(')
    end = generated.index('static int horizon_server_handle_terminate_thread(', start)
    handlers = generated[start:end]
    assert expected in handlers
    with tempfile.TemporaryDirectory(prefix='fex_runtime_fixes_suspend_') as temporary:
        work = Path(temporary)
        (work / 'fex_self_suspend_handlers.inc').write_text(handlers)
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
            '-pthread', '-I' + str(native_path.parent), '-I' + str(work),
            str(ROOT / 'tests/fex_self_suspend_native.c'), '-o', str(work / 'test')]
        build = subprocess.run(command, capture_output=True, text=True, timeout=60)
        assert build.returncode == 0, build.stderr
        run = subprocess.run([str(work / 'test')], capture_output=True, text=True, timeout=65)
        assert run.returncode == 0 and not run.stderr, run.stderr
        assert 'PASS self-suspend:' in run.stdout
        return {'passed': True, 'command': command, 'stdout': run.stdout,
                'compile_stderr': build.stderr, 'source_sha256': digest(handlers.encode())}


def expect_red(source, suite, scenario, reason):
    report = tests.compile_run(source, suite, scenario, check=False)
    assert report['compile_returncode'] == 0 and not report['compile_stderr'], report
    assert not report['passed'] and len(report['runs']) == 1, report
    run = report['runs'][0]
    if reason == 'timeout':
        assert run['timed_out'], report
    else:
        assert not run['timed_out'] and run['returncode'] != 0 and reason in run['stderr'], report
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Exact pinned source file/root')
    parser.add_argument('--native-source', required=True, type=Path, help='Unmodified prepared native source file/root')
    parser.add_argument('--generated-source', type=Path, help='Optional final prepared source; test as-is without patching')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    paths = [source_file(args.source), source_file(args.native_source)]
    if args.generated_source:
        paths.append(source_file(args.generated_source))
    raw = [path.read_bytes() for path in paths]
    source, native = [data.decode() for data in raw[:2]]
    provenance = verify_provenance(source)
    generated, native_generated = tests.patched(source), tests.patched(native)
    report = {'passed': False, 'hardware_tested': False, 'shipping_binary_built': False,
              'sanitizers': ['address', 'undefined'], 'provenance': provenance,
              'source_paths': [str(path) for path in paths],
              'source_hashes_before': [digest(data) for data in raw],
              'unchanged_functions': {'pinned': verify_scope(source, generated),
                                      'native': verify_scope(native, native_generated)},
              'fail_closed': verify_fail_closed(source)}
    composition = verify_composition(source)
    report['sibling_patch_order_identical'] = True
    red = [expect_red(source, 'timers', 'normal', '!objects[0].signaled'),
           expect_red(source, 'affinity', 'normal', 'observed->core_mask == expected_cached')]
    upstream = upstream_timer(source)
    literal_backport = source
    module = tests.patch_module()
    for scope, before, after in module.TIMER_EDITS:
        literal_backport = module._edit(literal_backport, scope, before, after)
    assert upstream == literal_backport, 'Literal upstream table differs from retained patch'
    report['literal_upstream_backport_verified'] = True
    red.append(expect_red(upstream, 'timers', 'normal', 'last_reply.signaled && objects[0].signaled'))
    for case, reason in (('rearm-poll', 'clock_ns100 == start'),
                         ('cancel-poll', 'sleeps == 4'),
                         ('relative-overflow', 'signed integer overflow'),
                         ('periodic-overflow', 'signed integer overflow'),
                         ('periodic-catchup', 'timeout')):
        red.append(expect_red(upstream, 'timers', case, reason))
    report['red'] = red
    report['green'] = []
    fixture = (ROOT / 'tests/fex_runtime_fixes_pinned.c').read_text()
    report['generated_hashes'] = {'pinned': digest(generated.encode()), 'native': digest(native_generated.encode())}
    for label, candidate in (('retained_pin', tests.patched(fixture)), ('full_pin', generated),
                             ('native_prepared', native_generated), ('sync_composition', composition)):
        for suite in ('timers', 'affinity'):
            result = tests.compile_run(candidate, suite)
            result['input'] = label
            report['green'].append(result)
    report['self_suspend'] = self_suspend(paths[1], native_generated)
    if args.generated_source:
        final = raw[2].decode()
        report['generated_source_sha256'] = digest(raw[2])
        report['generated_source_runs'] = [tests.compile_run(final, suite) for suite in ('timers', 'affinity')]
        report['generated_source_self_suspend'] = self_suspend(paths[2], final)
    # Mutation controls demonstrate expiry injection and running-timer polling
    # independently; tests cannot pass merely by changing set_timer's signal.
    mutants = [('missing_expiry_update',
                generated.replace('        horizon_server_update_timers_locked();\n', '', 1),
                'normal', 'locked && ns > 0'),
               ('missing_timer_poll',
                generated.replace('entry->object->type == HORIZON_SERVER_OBJECT_TIMER && entry->object->timer_when',
                                  'entry->object->type == HORIZON_SERVER_OBJECT_TIMER && 0', 1),
                'rearm-poll', 'clock_ns100 == start')]
    report['mutation_controls'] = []
    for label, candidate, scenario, reason in mutants:
        assert candidate != generated
        result = expect_red(candidate, 'timers', scenario, reason)
        result['mutation'] = label
        report['mutation_controls'].append(result)
    assert [path.read_bytes() for path in paths] == raw, 'Source input changed during read-only audit'
    report['inputs_unchanged'] = True
    report['toolchain'] = subprocess.check_output(shlex.split(os.environ.get('CC', 'cc')) +
                                                ['--version'], text=True)
    owned = ('tools/fex_runtime_fixes.py', 'tests/fex_runtime_fixes.py',
             'tests/fex_runtime_fixes_timer.c', 'tests/fex_runtime_fixes_affinity.c',
             'tests/fex_runtime_fixes_pinned.c', 'tests/fex_runtime_fixes_provenance.json',
             'tests/fex_runtime_fixes_upstream.patch', 'tests/fex_runtime_fixes_verify.py')
    report['test_file_hashes'] = {name: digest((ROOT / name).read_bytes()) for name in owned}
    report['passed'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'report': str(args.output),
                      'green_binaries': len(report['green']), 'expected_red': len(red),
                      'mutation_controls': len(report['mutation_controls']),
                      'inputs_unchanged': True, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
