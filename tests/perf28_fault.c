#include <assert.h>
#include <stdlib.h>
#include <pthread.h>
#include "../src/runtime/pes13_perf28_fault.h"

static struct {
    unsigned char caller[256], lookup[1024], stack[128], object[64], table[3000*PES28_STRIDE];
    unsigned int reads, table_reads, emits;
    int fail_table, fail_stack, fail_object;
    char last[256];
} mem;
static struct pes28_fault fault = {0xc0000005u,4,0,0x115c36f,0x2000,0,0x100000,0x100000,0,4,0,0x386,1};

static int reader(void *opaque, uint32_t at, void *out, size_t n)
{
    (void)opaque; ++mem.reads;
    assert(n <= 128); assert((uint64_t)at + n <= UINT64_C(0x100000000));
#define REGION(base, field) if (at >= (base) && (uint64_t)at + n <= (base) + sizeof(mem.field)) { memcpy(out, mem.field + at - (base), n); return 1; }
    REGION(0x115c300u, caller)
    REGION(0x438b40u, lookup)
    if (!mem.fail_stack) { REGION(0x2000u, stack) }
    if (!mem.fail_object) { REGION(0x3000u, object) }
    if (at >= 0x100000u && at < 0x100000u + sizeof(mem.table)) {
        ++mem.table_reads;
        if (mem.fail_table) return 0;
        REGION(0x100000u, table)
    }
    return 0;
#undef REGION
}
static void emit(void *opaque, const char *s)
{
    (void)opaque; ++mem.emits;
    assert(strlen(s) < 256); snprintf(mem.last, sizeof(mem.last), "%s", s);
}
static const struct pes28_io io = {reader, emit, NULL};
static void prepare(uint32_t count)
{
    uint32_t object = 0x3000;
    memcpy(mem.stack+0x1c, &object, sizeof(object));
    memcpy(mem.object+0x30, &count, sizeof(count));
    mem.reads = mem.table_reads = mem.emits = 0;
    mem.fail_stack = mem.fail_object = mem.fail_table = 0;
    for (unsigned i = 0; i < 3000; ++i) {
        uint16_t key = (uint16_t)i;
        memcpy(mem.table+i*PES28_STRIDE, &key, sizeof(key));
    }
}
static void capture(void)
{
    unsigned int once = 0;
    struct pes28_fault before = fault;
    assert(pes28_capture(&once, &fault, &io));
    assert(!memcmp(&fault, &before, sizeof(fault)));
    unsigned reads = mem.reads, emits = mem.emits;
    assert(!pes28_capture(&once, &fault, &io));
    assert(mem.reads == reads && mem.emits == emits);
    assert(emits <= 100 && reads < 2200);
}
static unsigned int concurrent_once, concurrent_read_count, concurrent_emit_count;
static int concurrent_read(void *p, uint32_t at, void *out, size_t n)
{
    (void)p; (void)at; (void)out; (void)n;
    __atomic_fetch_add(&concurrent_read_count, 1, __ATOMIC_RELAXED); return 0;
}
static void concurrent_emit(void *p, const char *s)
{
    (void)p; (void)s; __atomic_fetch_add(&concurrent_emit_count, 1, __ATOMIC_RELAXED);
}
static void *race(void *p)
{
    (void)p; const struct pes28_io concurrent_io = {concurrent_read, concurrent_emit, NULL};
    pes28_capture(&concurrent_once, &fault, &concurrent_io); return NULL;
}
int main(int argc, char **argv)
{
    assert(argc == 2); FILE *f = fopen(argv[1], "rb"); assert(f);
    assert(fread(mem.caller+0x28, 1, 88, f) == 88); fclose(f);
    prepare(1000); capture();
    assert(strstr(mem.last, "scanned=1000 expected=1000 capped=0 matches=1 descending_adjacent=0 failed=0"));
    prepare(3000); capture(); assert(strstr(mem.last, "scanned=2048 expected=3000 capped=1"));
    prepare(0); capture(); assert(strstr(mem.last, "scanned=0 expected=0"));
    prepare(UINT32_MAX); capture(); assert(strstr(mem.last, "invalid inferred range")); assert(!mem.table_reads);
    prepare(1000); mem.fail_table=1; capture(); assert(mem.table_reads==8); assert(strstr(mem.last,"failed=8"));
    prepare(1000); mem.fail_stack=1; capture(); assert(!mem.table_reads); assert(strstr(mem.last,"unavailable"));
    prepare(1000); mem.fail_object=1; capture(); assert(!mem.table_reads);
    prepare(1000); fault.esp=0xfffffff0u; capture(); assert(!mem.table_reads); fault.esp=0x2000;
    prepare(1000); fault.ebx=0; capture(); assert(!mem.table_reads); fault.ebx=0x100000;
    prepare(1000); uint16_t badkey=0; memcpy(mem.table+500*PES28_STRIDE,&badkey,2); capture();
    assert(strstr(mem.last,"descending_adjacent=1"));
    prepare(1000); mem.caller[0x56]^=1; unsigned int once=0;
    assert(!pes28_capture(&once,&fault,&io)); assert(!mem.table_reads); assert(strstr(mem.last,"fingerprint"));
    mem.caller[0x56]^=1;
    for (unsigned i=0;i<5;++i) {
        prepare(1000); struct pes28_fault other=fault; once=0;
        if(i==0) other.identity=0;
        if(i==1) other.status=0;
        if(i==2) other.eip++;
        if(i==3) other.address++;
        if(i==4) other.access=1;
        assert(!pes28_capture(&once,&other,&io)); assert(!once && !mem.reads && !mem.emits);
    }
    unsigned char byte; unsigned reads=mem.reads;
    assert(!pes28_read(&io,UINT64_C(0x100000000),&byte,1));
    assert(!pes28_read(&io,UINT32_MAX,&byte,2)); assert(reads==mem.reads);
    pthread_t threads[8];
    for(unsigned i=0;i<8;++i) assert(!pthread_create(&threads[i],NULL,race,NULL));
    for(unsigned i=0;i<8;++i) assert(!pthread_join(threads[i],NULL));
    assert(concurrent_read_count==1 && concurrent_emit_count==1);
    puts("PERF28 bounded read-only capture, real instruction signature, corrupt inputs, one-shot concurrency: PASS");
    return 0;
}
