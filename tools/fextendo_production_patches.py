"""Quiet normal launch; startup console and bounded error files on debug launch."""
import re


def apply(source):
    changed = set()

    def one(data, old, new):
        assert data.count(old) == 1, (old[:140], data.count(old))
        return data.replace(old, new)

    def body(data, signature, replacement):
        assert data.count(signature) == 1, signature
        start = data.index('{', data.index(signature) + len(signature))
        end, depth = start + 1, 1
        while depth:
            depth += (data[end] == '{') - (data[end] == '}')
            end += 1
        return data[:start] + '{\n' + replacement + '\n}' + data[end:]

    def edit(name, fn):
        p = source / name
        before = p.read_text()
        after = fn(before)
        assert before != after, name
        p.write_text(after)
        changed.add(name)

    def runtime(data):
        assert '#define FX_APP_VERSION "0.3.9-kit15"' in data
        data = one(data, '#include <switch.h>', '#include <switch.h>\n#define FX_SCREEN_DEBUG 1\n#include "fextendo_launch_debug.h"\n#include "fextendo_launch_memory.h"\n#include "fextendo_startup_heap.h"\nvoid wine_nx_transition_event(unsigned,unsigned,uint64_t,uint64_t);')
        data = one(data, '    if (!fx_silent_io_init()) return 1;',
                   '    if (!fx_launch_memory_validate()) return 0;\n    if (!fx_silent_io_init()) return 1;')
        data = one(data, '        __atomic_store_n(&fx_history_tick,armGetSystemTick(),__ATOMIC_RELEASE);',
            '    {\n        __atomic_store_n(&fx_history_tick,armGetSystemTick(),__ATOMIC_RELEASE);\n'
            '        fx_launch_debug_log("[FRAME] first game frame presented");\n    }')
        for line in ('#include "fextendo_transition_trace.h"', '#include "fextendo_transition_alloc.h"',
                     '#include "fextendo_live_trace.h"', '#define FX_NATIVE_ABORT_DETAIL 1',
                     '#include "fextendo_diagnostics.h"', '        fx_diagnostics_tick(ticks);',
                     '    fx_crash_bootstrap();', '    fx_crash_settings(fx_ui_view.selected,fx_ui_view.renderer);'):
            data = one(data, line, '')
        data = one(data, '        fx_production_maintenance_tick(++ticks);',
                   '        fx_production_maintenance_tick(++ticks);\n        if(ticks%5==0)fx_debug_file_tick();')
        # These callbacks remain referenced by the frozen bridge. Keep only
        # bounded screen messages; no observer, thread suspension or file API.
        anchor = '#include "fextendo_rust_heap.h"'
        callbacks = '''void wine_nx_transition_fex_image(uint64_t base,uint64_t size) {(void)base;(void)size;}
void wine_nx_transition_event(unsigned kind,unsigned code,uint64_t detail,uint64_t address) {
    fx_launch_debug_log("[FAILURE] kind=%u code=%08x detail=%llu address=%llx",kind,code,
        (unsigned long long)detail,(unsigned long long)address);
}
'''
        data = one(data, anchor, callbacks + anchor)
        data = one(data, '(void)r; (void)fd; wine_nx_transition_text(data,size);',
                   '(void)r; (void)fd; wine_nx_launch_debug_write(data,size);')
        data = body(data, 'void wine_nx_runtime_std_write( int stream, const char *data, size_t size )\n',
                    '    (void)stream; wine_nx_launch_debug_write(data,size);')
        data = body(data, 'void wine_nx_runtime_trace( const char *msg )\n',
                    '    fx_crash_failure_line(msg);\n    fx_launch_debug_log("%s",msg?msg:"");')
        data = body(data, 'static void log_line( const char *fmt, ... )\n', '''    if(!wine_nx_launch_debug_active())return;
    int saved=errno;char line[768];va_list args;va_start(args,fmt);
    int n=vsnprintf(line,sizeof(line)-1,fmt,args);va_end(args);
    if(n>0){size_t len=(unsigned)n<sizeof(line)-1?(size_t)n:sizeof(line)-2;
        line[len++]='\\n';wine_nx_launch_debug_write(line,len);}
    errno=saved;''')
        # Never enable verbose per-operation tracing, even for a debug launch.
        data = one(data, '        options[0].flags = 0;', '        options[0].flags = wine_nx_launch_debug_flags(NULL);')
        data = one(data, '    if(!fx_owned())return;\n    pthread_mutex_lock(&fx_ui_lock);',
                   '    fx_launch_debug_log("[STAGE] %s",text);\n    if(!fx_owned())return;\n    pthread_mutex_lock(&fx_ui_lock);')
        # Explicit lengths preserve the NUL-separated guest environment; there
        # is no global WINEDEBUG parser (main_argv is absent on this platform).
        old = 'const char trace_key[] = "FEXTENDO_TRACE=0\\0DXVK_LOG_LEVEL=none\\0DXVK_LOG_PATH=none\\0WINEDEBUG=-all";'
        new = '''const char quiet_key[] = "FEXTENDO_TRACE=0\\0DXVK_LOG_LEVEL=none\\0DXVK_LOG_PATH=none\\0WINEDEBUG=-all";
        const char debug_key[] = "FEXTENDO_TRACE=0\\0DXVK_LOG_LEVEL=none\\0DXVK_LOG_PATH=none\\0WINEDEBUG=err+all,warn+all";
        const int screen_debug=wine_nx_launch_debug_active();
        const char *trace_key=screen_debug?debug_key:quiet_key;
        const size_t trace_bytes=screen_debug?sizeof(debug_key):sizeof(quiet_key);'''
        data = one(data, old, new).replace('sizeof(trace_key)', 'trace_bytes')
        data = one(data, '(" RUNTIME_DIR "/std*.txt)', '(debug capture)')
        # Legacy debug files/INI values cannot turn file profiling back on.
        assert '"profile", "controller_trace"' in data
        return data

    edit('wine-nx-probe/source/runtime.c', runtime)
    # The builder restores this pinned helper before every patch pass.
    edit('wine-nx-probe/source/pes13_preload.c', lambda d: one(d,
         'Result __wrap_appletInitialize(void)\n{\n    hook_calls++;',
         'Result __wrap_appletInitialize(void)\n{\n'
         '    extern int wine_nx_launch_memory_compatible(void);\n'
         '    if (!wine_nx_launch_memory_compatible()) return __real_appletInitialize();\n'
         '    hook_calls++;'))
    edit('wine-nx-probe/source/thread_profile.c',
         lambda d: one(d, '#include "fextendo_live_threads.h"', '/* No diagnostic thread suspension in production. */'))

    def vulkan(data):
        data = one(data, 'extern unsigned wine_nx_transition_begin(unsigned,uint64_t);\nextern void wine_nx_transition_end(unsigned,int);', '')
        data, n = re.subn(r'    \{ unsigned fx_token=wine_nx_transition_begin\([^\n]+\);\n'
                          r'(    params->result = [^\n]+;)\n    wine_nx_transition_end\(fx_token,params->result\); \}', r'\1', data)
        assert n == 34, n
        return data
    edit('dlls/winevulkan/vulkan_thunks.c', vulkan)

    def cmake(data):
        # Keep native thread stack and Rust allocation wrappers, remove only
        # the observers. Never alter driver dependencies or memory policies.
        data, n = re.subn(r'^target_link_options\(wine-nx-runtime PRIVATE -Wl,--wrap=malloc [^\n]+\)\n', '', data, flags=re.M)
        assert n == 1, n
        assert '--wrap=abort' in data
        assert '--wrap=threadCreate' in data and '__rust' in data
        return data
    edit('wine-nx-probe/CMakeLists.txt', cmake)
    formatter = '''    extern int wine_nx_launch_debug_active(void);
    extern void wine_nx_launch_debug_write(const char *,size_t);
    if(!wine_nx_launch_debug_active())return;
    int saved=errno;char line[768];va_list args;va_start(args,fmt);
    int n=vsnprintf(line,sizeof(line)-1,fmt,args);va_end(args);
    if(n>0){size_t len=(unsigned)n<sizeof(line)-1?(size_t)n:sizeof(line)-2;
        line[len++]='\\n';wine_nx_launch_debug_write(line,len);}
    errno=saved;'''
    edit('dlls/ntdll/unix/horizon.c', lambda d: body(d, 'void horizon_trace( const char *fmt, ... )\n', formatter))

    def debug(data):
        data = one(data, 'static unsigned char default_flags =',
            'extern int wine_nx_launch_debug_active(void);\nextern void wine_nx_launch_debug_write(const char *,size_t);\n'
            'extern unsigned char wine_nx_launch_debug_flags(const char *);\nstatic unsigned char default_flags =')
        data = body(data, 'unsigned char __cdecl __wine_dbg_get_channel_flags( struct __wine_debug_channel *channel )\n',
                    '    channel->flags=wine_nx_launch_debug_flags(channel->name);\n    return channel->flags;')
        data = body(data, 'static int wine_nx_dbg_write( const char *str, unsigned int str_len )\n',
                    '    wine_nx_launch_debug_write(str,str_len);\n    return str_len;')
        data = body(data, 'int __cdecl __wine_dbg_output( const char *str )\n', '''    if(!wine_nx_launch_debug_active())return strlen(str);
    struct debug_info *info=get_info();
    const char *end=strrchr(str,'\\n');int ret=0;
    if(end){ret+=append_output(info,str,end+1-str);
        wine_nx_launch_debug_write(info->output,info->out_pos);info->out_pos=0;str=end+1;}
    if(*str)ret+=append_output(info,str,strlen(str));return ret;''')
        return data
    edit('dlls/ntdll/unix/debug.c', debug)
    return sorted(changed)
