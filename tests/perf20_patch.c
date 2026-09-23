#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../src/runtime/pes13_perf19.h"
#include "../src/runtime/pes13_perf20.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }

static void read_fixture(const char *directory, const char *name, void *out, size_t n)
{
    char path[1024]; snprintf(path,sizeof(path),"%s/%s",directory,name);
    FILE *f=fopen(path,"rb"); assert(f);
    assert(fread(out,1,n,f)==n && fgetc(f)==EOF); fclose(f);
}

int main(int argc, char **argv)
{
    uint32_t matrix[7064/4], worker[376/4], original[376/4];
    unsigned char matrix_guest[656], worker_guest[63];
    dynablock_t db={0};
    assert(argc==5); assert(!perf17_policy_main(2,argv));
    read_fixture(argv[2],"slot-0-arm64.bin",matrix,sizeof(matrix));
    read_fixture(argv[2],"slot-0-x86.bin",matrix_guest,sizeof(matrix_guest));
    read_fixture(argv[3],"slot-2-arm64.bin",worker,sizeof(worker));
    read_fixture(argv[3],"slot-2-x86.bin",worker_guest,sizeof(worker_guest));
    memcpy(original,worker,sizeof(worker));
    pes17_identity=1; pes19_mode=1; pes20_mode=1;
    db.block=matrix; db.x64_addr=(void *)0x112fb90; db.x64_readaddr=(uintptr_t)matrix_guest;
    db.native_size=sizeof(matrix); db.x64_size=sizeof(matrix_guest); db.is32bits=1;
    wine_nx_perf19_patch(&db); assert(pes19_applied==1);
    wine_nx_perf20_patch(&db); assert(!pes20_seen);
    assert(pes19_hash(matrix,sizeof(matrix))==UINT64_C(0x28767002a96c6b9b));
    db.block=worker; db.x64_addr=(void *)0x937990; db.x64_readaddr=(uintptr_t)worker_guest;
    db.native_size=sizeof(worker); db.x64_size=sizeof(worker_guest);
    pes20_mode=0; wine_nx_perf20_patch(&db); assert(!pes20_seen);
    pes20_mode=1; pes17_identity=-1; wine_nx_perf20_patch(&db); assert(!pes20_seen);
    pes17_identity=1; db.is32bits=0; wine_nx_perf20_patch(&db); assert(!pes20_seen); db.is32bits=1;
    db.x64_addr=(void *)0x1c9a000; wine_nx_perf20_patch(&db); assert(!pes20_seen);
    db.x64_addr=(void *)0x1c99fff; wine_nx_perf20_patch(&db); assert(!pes20_seen);
    db.x64_addr=(void *)0x937990; db.sep_size=1; wine_nx_perf20_patch(&db);
    db.sep_size=0; db.callret_size=1; wine_nx_perf20_patch(&db);
    db.callret_size=0; db.native_size=65540; wine_nx_perf20_patch(&db);
    db.native_size=sizeof(worker); assert(pes20_scope==3);
    assert(!memcmp(worker,original,sizeof(worker)));
    wine_nx_perf20_patch(&db);
    assert(pes20_blocks==1 && pes20_merged==5 && pes20_guards==6 && pes20_runs==1);
    FILE *f=fopen(argv[4],"wb"); assert(f);
    assert(fwrite(worker,1,sizeof(worker),f)==sizeof(worker)); fclose(f);
    wine_nx_perf20_patch(&db); assert(pes20_blocks==1 && pes20_flow==1);
    /* The precise capture bucket must not be consumed by a preceding block. */
    memset(pes17_snapshots,0,sizeof(pes17_snapshots)); pes17_capture=1;
    db.x64_addr=(void *)0x93b83b; db.x64_size=18; wine_nx_perf20_capture(&db);
    assert(!pes17_snapshots[0].state);
    db.x64_addr=(void *)0x93b850; db.x64_size=63; wine_nx_perf20_capture(&db);
    assert(pes17_snapshots[0].state==2 && pes17_snapshots[0].x86_bytes==63);
    assert(!memcmp(pes17_snapshots[0].arm,worker,sizeof(worker)));
    wine_nx_perf20_report();
    puts("PERF20 image/bounds/secondary-entry/control/repeat guards, PERF19 retention and exact hotspot capture PASS");
    return 0;
}
