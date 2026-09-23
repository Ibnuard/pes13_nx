#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../src/runtime/pes13_perf19.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }

static void read_fixture(const char *directory, const char *name, void *out, size_t n)
{
    char path[1024]; snprintf(path,sizeof(path),"%s/%s",directory,name);
    FILE *f=fopen(path,"rb"); assert(f);
    assert(fread(out,1,n,f)==n && fgetc(f)==EOF); fclose(f);
}

int main(int argc, char **argv)
{
    uint32_t native[7064/4], original[7064/4]; unsigned char guest[656];
    dynablock_t db={0};
    assert(argc==4); assert(!perf17_policy_main(2,argv));
    read_fixture(argv[2],"slot-0-arm64.bin",native,sizeof(native));
    read_fixture(argv[2],"slot-0-x86.bin",guest,sizeof(guest));
    memcpy(original,native,sizeof(native));
    db.block=native; db.x64_readaddr=(uintptr_t)guest;
    db.x64_addr=(void *)0x112fb90; db.native_size=sizeof(native);
    db.x64_size=sizeof(guest); db.is32bits=1;
    pes19_mode=0; wine_nx_perf19_patch(&db); assert(!pes19_seen);
    pes19_mode=1; pes17_identity=-1; wine_nx_perf19_patch(&db); assert(!pes19_seen);
    pes17_identity=1; db.x64_addr=(void *)0x112fb91;
    wine_nx_perf19_patch(&db); assert(!pes19_seen);
    db.x64_addr=(void *)0x112fb90; db.native_size--;
    wine_nx_perf19_patch(&db); assert(pes19_rejected==1);
    db.native_size++; db.sep_size=1;
    wine_nx_perf19_patch(&db); assert(pes19_rejected==2); db.sep_size=0;
    db.callret_size=1; wine_nx_perf19_patch(&db); assert(pes19_rejected==3); db.callret_size=0;
    guest[100]^=1; wine_nx_perf19_patch(&db); assert(pes19_rejected==4); guest[100]^=1;
    native[100]^=1; wine_nx_perf19_patch(&db); assert(pes19_rejected==5); native[100]^=1;
    assert(!memcmp(original,native,sizeof(native)) && !pes19_applied);
    wine_nx_perf19_patch(&db); assert(pes19_applied==1);
    assert(pes19_hash(native,sizeof(native))==UINT64_C(0x28767002a96c6b9b));
    FILE *f=fopen(argv[3],"wb"); assert(f);
    assert(fwrite(native,1,sizeof(native),f)==sizeof(native)); fclose(f);
    wine_nx_perf19_patch(&db); assert(pes19_applied==1 && pes19_rejected==6);
    assert(pes19_hash(native,sizeof(native))==UINT64_C(0x28767002a96c6b9b));
    wine_nx_perf19_report();
    puts("PERF19 exact bytes, no partial writes, identity/scope/control, aliases and repeat rejection PASS");
    return 0;
}
