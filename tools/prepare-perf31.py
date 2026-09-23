"""Versioned copies keep the shipped PERF30 headers and evidence immutable."""
from pathlib import Path
from perf17_patches import once
p=Path(__file__).resolve().parents[1]
def rename(s):return s.replace('PES30','PES31').replace('pes30','pes31').replace('perf30','perf31').replace('STAGE30','STAGE31').replace('ACTIVE30','ACTIVE31').replace('SLOW30','SLOW31').replace('VALUE30','VALUE31').replace('PERF30','PERF31')
for name in ('pes13_perf30.h','pes13_perf30_core.h','pes13_perf30_runtime.h'):
    text=rename((p/'src/runtime'/name).read_text())
    if name.endswith('perf30.h'):
        text=once(text,'PES31_AUDIO_PUMP, PES31_AUDIO_RELEASE, PES31_STAGES',
            'PES31_AUDIO_PUMP, PES31_AUDIO_RELEASE, PES31_SUBMIT_API, PES31_SUBMIT_CREATE,\n'
            '    PES31_SUBMIT_DESTROY, PES31_SIGNAL_UNWRAP, PES31_TIMELINE_INSTALL,\n'
            '    PES31_TIMELINE_GC, PES31_FENCE_QUERY, PES31_FENCE_WAIT, PES31_ERROR_SCAN, PES31_STAGES')
        text=once(text,'#define PES31_TIME', 'extern int wine_nx_perf31_poll_mode(void);\nextern void wine_nx_perf31_poll_count(int deferred);\n#define PES31_TIME')
    if name.endswith('runtime.h'):
        text=once(text,'"audio_pump","audio_release"',
            '"audio_pump","audio_release","submit_api","submit_create","submit_destroy",'
            '"signal_unwrap","timeline_install","timeline_gc","fence_query","fence_wait","error_scan"')
        text=once(text,'void wine_nx_perf31_init(void)', '''static unsigned pes31_poll_enabled;
static uint64_t pes31_poll_checked, pes31_poll_deferred;
int wine_nx_perf31_poll_mode(void) { return __atomic_load_n(&pes31_poll_enabled,__ATOMIC_RELAXED); }
void wine_nx_perf31_poll_count(int deferred) {
    __atomic_add_fetch(deferred ? &pes31_poll_deferred : &pes31_poll_checked,1,__ATOMIC_RELAXED);
}
void wine_nx_perf31_init(void)''')
        text=once(text,'    __atomic_store_n(&pes31_enabled,enabled,__ATOMIC_RELEASE);', '''    __atomic_store_n(&pes31_enabled,enabled,__ATOMIC_RELEASE);
    f=fopen("sdmc:/switch/pes13-nx/perf31-fence-poll.txt","r");
    unsigned poll=f ? fgetc(f)=='1' : 0;
    if(f) fclose(f);
    __atomic_store_n(&pes31_poll_enabled,poll,__ATOMIC_RELEASE);''')
        text=once(text,'    if(!enabled) return;', '''    log_line("[POLL31] enabled=%u error_scan_checked=%llu error_scan_deferred=%llu; cumulative; native fence query retained",
        wine_nx_perf31_poll_mode(),(unsigned long long)__atomic_load_n(&pes31_poll_checked,__ATOMIC_RELAXED),
        (unsigned long long)__atomic_load_n(&pes31_poll_deferred,__ATOMIC_RELAXED));
    if(!enabled) return;''')
    (p/'src/runtime'/name.replace('30','31')).write_text(text)
path=p/'tools/perf30_patches.py'
(p/'tools/perf31_patches.py').write_text(rename(path.read_text()))
path=p/'tools/run-perf30-build.py'
(p/'tools/run-perf31-build.py').write_text(rename(path.read_text()))
path=p/'tests/perf30_metrics.c'
(p/'tests/perf31_metrics.c').write_text(rename(path.read_text()))
path=p/'tests/perf30_metrics.py'
(p/'tests/perf31_metrics.py').write_text(rename(path.read_text()))
