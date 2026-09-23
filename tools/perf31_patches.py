"""Same PERF29 control behavior with bounded native driver and audio timing."""
import perf29_patches
from perf17_patches import once
from perf27_patches import function_span
adapt_profile=perf29_patches.adapt_profile

def patch_audio(text,project):
    text='#include "'+str(project/'src/runtime/pes13_perf31.h')+'"\n'+text
    # Return paths remain in the implementation; the wrapper always closes
    # its measurement, including failed audout calls.
    a,b=function_span(text,'nx_pump');body=text[a:b].replace('nx_pump(', 'pes31_pump_impl(',1)
    wrapper='''
static void nx_pump(struct nx_audio_stream *s)
{
    PES31_TIME(PES31_AUDIO_PUMP, s, pes31_pump_impl(s));
    wine_nx_perf31_value(PES31_AUDIO_HELD, s->held);
    wine_nx_perf31_value(PES31_AUDIO_SUBMITTED, s->submitted);
    wine_nx_perf31_value(PES31_AUDIO_PLAYED, s->played);
}
'''
    text=text[:a]+body+wrapper+text[b:]
    a,b=function_span(text,'nx_release_render_buffer');body=text[a:b].replace('nx_release_render_buffer(', 'pes31_release_impl(',1)
    body=once(body,'    pthread_mutex_lock(&audio_lock);',
        '    PES31_TIME(PES31_AUDIO_LOCK, s, pthread_mutex_lock(&audio_lock));')
    wrapper='''
static NTSTATUS nx_release_render_buffer(void *args)
{
    NTSTATUS result;
    PES31_TIME(PES31_AUDIO_RELEASE, 0, result = pes31_release_impl(args));
    return result;
}
'''
    text=text[:a]+body+wrapper+text[b:]
    a,b=function_span(text,'nx_timer_loop');body=text[a:b]
    body=once(body,'        pthread_mutex_lock(&audio_lock);',
        '        PES31_TIME(PES31_AUDIO_LOCK, s, pthread_mutex_lock(&audio_lock));')
    return text[:a]+body+text[b:]

def adapt_recipe(text):
    text=perf29_patches.adapt_recipe(text).replace('local/perf29','local/perf31')
    text=once(text,'mesa = root / "mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib"',
        'mesa = root / "perf31-mesa-sdk/lib"')
    text=once(text,'originals = {','audio_source = source / "source/audio_unix.c"\noriginals = {')
    text=once(text,'thunks_source, unix_source,','thunks_source, unix_source, audio_source,')
    return once(text,'    runtime_source.write_text(runtime_text)',
        '    runtime_source.write_text(runtime_text)\n'
        '    from perf31_patches import patch_audio\n'
        '    audio_text = patch_audio(originals[audio_source].decode(), project)\n'
        '    (project/"local/perf31/audio_unix.c").write_text(audio_text)\n'
        '    audio_source.write_text(audio_text)')

def adapt(cmake,dynarec,runtime,project):
    path=project/'tools/perf29_patches.py';ns={'__file__':str(path),'__name__':'perf31_base'}
    # Rebind new generated files, including the nested PERF28 adapter paths.
    exec(compile(path.read_text().replace('local/perf29','local/perf31'),str(path),'exec'),ns)
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    dynarec=once(dynarec,'    apply_box64_options();',
        '    apply_box64_options();\n    { extern void wine_nx_perf31_init(void); wine_nx_perf31_init(); }')
    runtime=once(runtime,'static void log_line(const char *fmt, ...);',
        'static void log_line(const char *fmt, ...);\n#include "'+str(project/'src/runtime/pes13_perf31_runtime.h')+'"')
    runtime=once(runtime,'    wine_nx_thread_report();','    pes31_report();\n    wine_nx_thread_report();')
    return cmake,dynarec,runtime
