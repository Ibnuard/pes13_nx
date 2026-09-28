"""Optional FEX3 self-suspend wake isolation; apply AFTER self-suspend + sync.

Only horizon.c/runtime.c change. Thread ABI and global select router stay intact.
Validate every owned slice before any replace; drift and reapplication fail closed.
"""
import hashlib
import re

HORIZON = 'dlls/ntdll/unix/horizon.c'
RUNTIME = 'wine-nx-probe/source/runtime.c'
BEGIN = '/* FEX3_RESUME_GATE_BEGIN */'
END = '/* FEX3_RESUME_GATE_END */'


def _function(text, name):
    matches = list(re.finditer(r'^static [^;\n]*\b' + re.escape(name) + r'\s*\(', text, re.M))
    if len(matches) != 1:
        raise ValueError('resume gate: missing/duplicate function ' + name)
    start = matches[0].start()
    brace = text.index('{', matches[0].end())
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def _once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('resume gate: source drift at ' + old[:90])
    return text.replace(old, new)


def apply(read, replace, project):
    source = read(HORIZON)
    if BEGIN in source or 'fex_resume_wait_locked' in source:
        raise ValueError('resume gate: already applied')
    if source.count('#define HORIZON_SERVER_WAIT_SLICE    200000LL\n') != 1:
        raise ValueError('resume gate: 20ms wait slice drift')
    threads = read('dlls/ntdll/unix/horizon_threads.h')
    if hashlib.sha256(threads.encode()).hexdigest() != '407d43efa59078ffbe92559fb1413287c343e4986126b4b317db3b441bc55765':
        raise ValueError('resume gate: thread ABI/helper drift')
    # Pin touched generated handlers, not the entire file: sibling independent
    # diagnostics may change other functions. Hashes from actual baseline.
    for name, digest in (
        ('horizon_server_handle_resume_thread', '6610689c2850e10f5de663b6b0193ee2eb06ddb1c28ab3516ae6f3f554500692'),
        ('horizon_server_end_thread_locked', 'a9d69c1ca9a19f292ac600fcb2d55b6f9f7db0297d1e490d20675c07f84b8310'),
        ('horizon_server_sleep_locked', '9a681e48148e34da03f484fbb293859c0da789e5641254ca1f373fda9870817a'),
    ):
        if hashlib.sha256(_function(source, name).encode()).hexdigest() != digest:
            raise ValueError('resume gate: source drift in ' + name)
    self_suspend = (project / 'src/runtime/fex_self_suspend.h').read_text()
    if source.count(self_suspend) != 1:
        raise ValueError('resume gate: self-suspend prerequisite/source drift')
    anchor = '#include "' + str(project / 'src/runtime/fex_sync_horizon.h') + '"'
    header = (project / 'src/runtime/fex_resume_runtime.h').read_text()
    changed = _once(source, anchor, anchor + '\n\n' + BEGIN + '\n' + header + END)
    changed = _once(changed,
        '            while (object->thread.suspend && !object->thread.terminated)\n'
        '                horizon_server_sleep_locked(HORIZON_SERVER_WAIT_SLICE);',
        '            fex_resume_wait_locked(object);')
    changed = _once(changed,
        '    if ((object = horizon_server_get_thread_locked( request->handle, &status )))\n'
        '        status = horizon_thread_resume( &object->thread, &reply.count );\n'
        '    horizon_server_signal_changed_locked();  /* the start gate */',
        '''    if ((object = horizon_server_get_thread_locked( request->handle, &status )))
    {
        status = horizon_thread_resume( &object->thread, &reply.count );
        if (!status && reply.count == 1)
        {
            ++fex_resume_counts.final;
            if (object->thread.self_suspended) fex_resume_wake_locked(object, 0);
            else if (!object->thread.started)
            {
                ++fex_resume_counts.start;
                horizon_server_signal_changed_locked();  /* real final start-gate resume */
            }
        }
        else ++fex_resume_counts.ignored;
    }
    else ++fex_resume_counts.ignored;''')
    changed = _once(changed,
        '    if (horizon_thread_mark_terminated( &thread->thread, horizon_server_now() ))\n'
        '        horizon_server_running_threads--;',
        '    if (horizon_thread_mark_terminated( &thread->thread, horizon_server_now() ))\n'
        '        horizon_server_running_threads--;\n'
        '    fex_resume_wake_locked(thread, 1);  /* before reference drop; keep broad notification below */')
    runtime = read(RUNTIME)
    startup = '    log_line("[FEX3-SYNC] startup targeted=%d; shared start/self-suspend gates preserved", wine_nx_fex_targeted_wake);'
    changed_runtime = _once(runtime, startup,
        startup.replace('shared start/self-suspend gates preserved',
                        'shared start gates preserved; self-suspend isolated') + '\n'
        '    log_line("[FEX3-RESUME] isolated self-suspend wake; final start-gate broadcast; 20ms recheck");')
    changed_runtime = _once(changed_runtime, 'static void *log_flusher( void *arg )\n{',
        'extern void wine_nx_fex_resume_report(void);\n\nstatic void *log_flusher( void *arg )\n{')
    cadence = '        if (ticks % 50 == 0) fex_sync_report();\n'
    changed_runtime = _once(changed_runtime, cadence, cadence +
        '        if (ticks % 50 == 0) wine_nx_fex_resume_report();\n')
    # Commit only after every prerequisite/anchor in BOTH files validated.
    replace(HORIZON, source, changed)
    replace(RUNTIME, runtime, changed_runtime)
