"""Compile the real patched fence wait against deterministic native-service stubs."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p/'tools'))
from perf31_mesa import patch,span
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'));w=p/'local/perf31'
src=root/'mesa-switch/src/nouveau/horizon/nouveau_horizon_channel.c';text=patch(src.name,src.read_text(),p)
a,b,start=span(text,'nouveau_horizon_fence_wait_impl')
function='static enum nouveau_horizon_status\n'+text[a:b]
fixture=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define MIN2(a,b) ((a)<(b)?(a):(b))
#define NOUVEAU_HORIZON_FENCE_POLL_NS UINT64_C(50000000)
enum nouveau_horizon_status { NOUVEAU_HORIZON_SUCCESS, NOUVEAU_HORIZON_ERROR_TIMEOUT,
    NOUVEAU_HORIZON_ERROR_INVALID_ARGUMENT,NOUVEAU_HORIZON_ERROR_DEVICE_LOST };
struct nouveau_horizon_device { int lost; };
struct nouveau_horizon_channel { int unused; };
struct nouveau_horizon_fence { int id; };
typedef struct nouveau_horizon_fence NvFence;
typedef int Result;
#define R_SUCCEEDED(x) ((x)==0)
static uint64_t now;
static int mode,queries,scans,deferrals,checked,native_status,scan_status,complete_after;
static int nouveau_horizon_fence_is_valid(const struct nouveau_horizon_fence *f) {return f->id>=0;}
static NvFence nouveau_horizon_native_fence(struct nouveau_horizon_fence f) {return f;}
static uint64_t os_time_get_nano(void) {return now;}
static int nouveau_horizon_timeout_ns_to_us(uint64_t n) {return (int)((n+999)/1000);}
static Result nvFenceWait(NvFence *f,int us) {
    (void)f;queries++;now+=(uint64_t)us*1000;
    return complete_after && queries>=complete_after ? 0 : native_status;
}
static enum nouveau_horizon_status nouveau_horizon_status_from_result(Result r,enum nouveau_horizon_status fallback) {
    (void)fallback;return (enum nouveau_horizon_status)r;
}
static void nouveau_horizon_device_mark_lost(struct nouveau_horizon_device *d) {d->lost=1;}
static bool nouveau_horizon_device_is_lost(struct nouveau_horizon_device *d) {return d->lost;}
static enum nouveau_horizon_status nouveau_horizon_device_scan_channel_errors(struct nouveau_horizon_device *d,uint32_t id,
        struct nouveau_horizon_channel *c) {(void)d;(void)id;(void)c;scans++;return scan_status;}
static int wine_nx_perf31_poll_mode(void) {return mode;}
static void wine_nx_perf31_poll_count(int deferred) {if(deferred)deferrals++;else checked++;}
struct pes31_token {int unused;};
enum {PES31_FENCE_QUERY,PES31_FENCE_WAIT,PES31_ERROR_SCAN};
static struct pes31_token wine_nx_perf31_enter(int stage,uintptr_t obj) {(void)stage;(void)obj;return (struct pes31_token){0};}
static void wine_nx_perf31_leave(struct pes31_token t) {(void)t;}
#define PES31_TIME(stage,obj,statement) do { statement; } while(0)
'''
tests=r'''
int main(void) {
    struct nouveau_horizon_device device={0}, other={0};struct nouveau_horizon_fence f={1},invalid={-1};
    mode=1;native_status=NOUVEAU_HORIZON_ERROR_TIMEOUT;
    assert(nouveau_horizon_fence_wait_impl(NULL,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_INVALID_ARGUMENT);
    assert(nouveau_horizon_fence_wait_impl(&device,&invalid,0,NULL)==0 && queries==0);
    for(int i=0;i<10000;i++)assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT);
    assert(queries==10000 && scans==1 && deferrals==9999);
    now=50000000;assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT);
    assert(scans==2); /* exact boundary */
    native_status=0;assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==0);assert(scans==2);
    native_status=NOUVEAU_HORIZON_ERROR_TIMEOUT;
    assert(nouveau_horizon_fence_wait_impl(&other,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT && scans==3);
    now=1;assert(nouveau_horizon_fence_wait_impl(&other,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT && scans==4);
    mode=0;int before=scans;
    for(int i=0;i<20;i++)assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT);
    assert(scans==before+20);
    mode=1;before=scans;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,123000,NULL)==NOUVEAU_HORIZON_ERROR_TIMEOUT);
    assert(scans==before+1); /* positive timeout never gated */
    complete_after=queries+2;before=scans;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,UINT64_MAX,NULL)==0 && scans==before+1);
    complete_after=0;device.lost=1;before=scans;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_DEVICE_LOST && scans==before);
    device.lost=0;native_status=NOUVEAU_HORIZON_ERROR_DEVICE_LOST;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_DEVICE_LOST && device.lost);
    device.lost=0;native_status=NOUVEAU_HORIZON_ERROR_TIMEOUT;scan_status=NOUVEAU_HORIZON_ERROR_DEVICE_LOST;now+=50000000;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_DEVICE_LOST);
    before=scans;
    assert(nouveau_horizon_fence_wait_impl(&device,&f,0,NULL)==NOUVEAU_HORIZON_ERROR_DEVICE_LOST && scans==before+1);
    struct pes31_poll_gate a={0},b={0};
    assert(!pes31_defer_error_scan(&a,1,7,0,0,1) && !pes31_defer_error_scan(&b,1,7,0,0,1));
    assert(pes31_defer_error_scan(&a,1,7,0,1,1) && pes31_defer_error_scan(&b,1,7,0,1,1));
    assert(!pes31_defer_error_scan(&a,1,8,0,1,1)); /* another channel must not starve */
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='perf31-poll-',dir=root) as temp:
    file=Path(temp)/'poll.c';exe=Path(temp)/'poll'
    file.write_text('#include "'+str(p/'src/runtime/pes13_perf31_poll.h')+'"\n'+fixture+function+tests)
    subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(file),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
files=['src/runtime/pes13_perf31_poll.h','tools/perf31_mesa.py','tests/perf31_poll.py']
(w/'poll-tests.json').write_text(json.dumps(dict(asan_ubsan='PASS',native_queries_retained=10000,
    optional_error_scans_same_tick=1,hardware_tested=False,
    original_source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
    source_sha256={f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in files}),indent=2)+'\n')
print('PERF31 real fence implementation: completion/timeout/error/control semantics and 10000-query scan bound PASS',flush=True)
