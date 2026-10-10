#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <time.h>
#include <sys/stat.h>
#include <pthread.h>

/* Only the platform boundary is substituted. The complete metadata and
 * observer implementation below is extracted verbatim from the shipped C. */
typedef uint64_t u64;
typedef struct { char name[768]; int type; int64_t file_size; } FsDirectoryEntry;
typedef struct { uint32_t magic; long index; size_t size; } fsdev_dir_t;
typedef struct { int device; void *dirStruct; } DIR_ITER;
typedef struct { DIR_ITER *dirData; } DIR;
typedef struct { size_t dirStateSize; } devoptab_t;
typedef struct { unsigned id; } FsFileSystem;
typedef struct { u64 created, modified, accessed; int is_valid; } FsTimeStampRaw;
typedef struct { uint16_t year; uint8_t month, day, hour, minute, second, pad; } TimeCalendarTime;
#define FSDEV_DIRITER_MAGIC 0x66736476
#define FsDirEntryType_File 1
#define FsDirEntryType_Dir 0
#define FS_MAX_PATH 769
#define R_FAILED(r) ((r)!=0)
static struct { fsdev_dir_t cursor; FsDirectoryEntry entries[2]; } batch;
static devoptab_t device={sizeof(batch)};
static FsFileSystem filesystem;
static FsTimeStampRaw timestamps;
static int translation_error, timestamp_error, conversion_error, debug_enabled;
static unsigned translation_calls, timestamp_calls, conversion_calls, clock_calls;
static unsigned long long fake_time=1000000;
static char trace[20000];
static unsigned traces;
static FsDirectoryEntry *fsdevDirGetEntries(fsdev_dir_t *p) { return (FsDirectoryEntry *)(p+1); }
static int FindDevice(const char *n) { assert(!strcmp(n,"sdmc:"));return 3; }
static const devoptab_t *GetDeviceOpTab(const char *n) { assert(!strcmp(n,"sdmc:"));return &device; }
static int fsdevTranslatePath(const char *p, FsFileSystem **f, char *out) {
    translation_calls++;assert(!strncmp(p,"sdmc:/",6));
    if(translation_error){errno=EIO;return -1;}
    *f=&filesystem;strcpy(out,p+5);return 0;
}
static int fsFsGetFileTimeStampRaw(FsFileSystem *f,const char *p,FsTimeStampRaw *t) {
    timestamp_calls++;assert(f==&filesystem && p[0]=='/');
    if(timestamp_error)return 3;
    *t=timestamps;return 0;
}
static int timeToPosixTimeWithMyRule(const TimeCalendarTime *c,u64 *value,int n,void *count) {
    conversion_calls++;assert(n==1 && !count);
    if(conversion_error)return 4;
    struct tm tm={.tm_year=c->year-1900,.tm_mon=c->month-1,.tm_mday=c->day,
                  .tm_hour=c->hour,.tm_min=c->minute,.tm_sec=c->second};
    *value=(u64)timegm(&tm)-7*3600;return 0;
}
static unsigned long long horizon_interrupt_time(void) {
    __atomic_add_fetch(&clock_calls,1,__ATOMIC_RELAXED);
    return __atomic_load_n(&fake_time,__ATOMIC_RELAXED);
}
int wine_nx_launch_debug_active(void) { return debug_enabled; }
static void horizon_trace(const char *fmt,...) {
    va_list ap;va_start(ap,fmt);size_t len=strlen(trace);
    vsnprintf(trace+len,sizeof(trace)-len,fmt,ap);va_end(ap);traces++;
}
/* PRODUCTION_IMPLEMENTATION */

static void *observe_worker(void *arg) {
    (void)arg;
    for(unsigned i=0;i<500;i++){
        unsigned t=horizon_dir_diag_begin(i);assert(t);
        __atomic_add_fetch(&fake_time,100,__ATOMIC_RELAXED);
        horizon_dir_diag_stage(t,3);horizon_dir_diag_end(t,1);
    }
    return NULL;
}
int main(void) {
    struct horizon_directory_file_entry hint={0};
    DIR_ITER iter={3,&batch.cursor};DIR dir={&iter};
    batch.cursor=(fsdev_dir_t){FSDEV_DIRITER_MAGIC,1,2};
    strcpy(batch.entries[1].name,"patch.adx");batch.entries[1].type=FsDirEntryType_File;
    batch.entries[1].file_size=0x100001234LL;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);
    assert(hint.metadata==1 && hint.file_size==0x100001234ULL);
    unsigned cases=1;
    horizon_dir_capture_metadata(&dir,"romfs:/patch","patch.adx",&hint);assert(!hint.metadata);
    iter.device=4;horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    iter.device=3;batch.cursor.magic=0;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.cursor.magic=FSDEV_DIRITER_MAGIC;batch.cursor.index=-1;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.cursor.index=2;horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.cursor.index=1;batch.cursor.size=3;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.cursor.size=2;batch.entries[1].file_size=-1;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.entries[1].file_size=128;batch.entries[1].type=FsDirEntryType_Dir;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    batch.entries[1].type=FsDirEntryType_File;
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","other.adx",&hint);assert(!hint.metadata);
    horizon_dir_capture_metadata(&dir,"sdmc:/patch",".",&hint);assert(!hint.metadata);
    memset(batch.entries[1].name,'x',sizeof(batch.entries[1].name));
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(!hint.metadata);
    cases+=11;
    strcpy(batch.entries[1].name,"patch.adx");
    horizon_dir_capture_metadata(&dir,"sdmc:/patch","patch.adx",&hint);assert(hint.metadata);
    struct stat st, expected;
    memset(&expected,0,sizeof(expected));expected.st_mode=S_IFREG|0666;
    expected.st_nlink=1;expected.st_size=128;
    timestamps=(FsTimeStampRaw){1720000000,1720010000,1720020000,1};
    expected.st_ctime=timestamps.created-25200;expected.st_mtime=timestamps.modified-25200;
    expected.st_atime=timestamps.accessed-25200;
    errno=ERANGE;
    assert(horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0)==1);
    assert(errno==ERANGE && !memcmp(&st,&expected,sizeof(st)) && conversion_calls==3);
    cases++;
    timestamps.is_valid=0;assert(horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0)==1);
    assert(!st.st_mtime && !st.st_ctime && !st.st_atime && conversion_calls==3);cases++;
    timestamps.is_valid=1;conversion_error=1;
    assert(horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0)==1);
    assert(st.st_mtime==(time_t)timestamps.modified && st.st_ctime==(time_t)timestamps.created);cases++;
    conversion_error=0;timestamp_error=1;st.st_size=999;
    assert(!horizon_dir_entry_stat("sdmc:/patch/deleted.adx",&hint,&st,0));
    assert(st.st_size==999 && errno==ERANGE);cases++;
    timestamp_error=0;translation_error=1;
    assert(!horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0) && errno==ERANGE);cases++;
    translation_error=0;unsigned previous=translation_calls;
    hint.metadata=0;assert(!horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0));
    hint.metadata=1;hint.file_size=UINT64_MAX;
    assert(!horizon_dir_entry_stat("sdmc:/patch/patch.adx",&hint,&st,0));
    hint.file_size=128;assert(!horizon_dir_entry_stat("romfs:/patch/patch.adx",&hint,&st,0));
    assert(translation_calls==previous);cases+=3;

    /* The compatibility fast path is limited to AFS asset-list entries.
     * Thousands of distinct names must not issue a timestamp/path IPC. */
    static const char *eligible[]={
        "sdmc:/switch/pes13-fex/drive_c/PES13/kitserver13/ISN PATCH 26/img/dt00_e.img/unnamed_1.adx",
        "sdmc:/GAME/KitServer13/Selector/A/B/IMG/DT01.IMG/file.bin",
        "sdmc:/kitserver/img/dt01.img/file.bin",
        "sdmc:/kitserver/img/./dt01.img/file.bin",
    };
    static const char *ordinary[]={
        "sdmc:/game/img/dt01.img/file.bin",
        "sdmc:/kitserver13-backup/img/dt01.img/file.bin",
        "sdmc:/kitserver13/GDB/uni/config.txt",
        "sdmc:/kitserver13/img/file.bin",
        "sdmc:/kitserver13/img/dt01.img/sub/file.bin",
        "sdmc:/kitserver13/img/dt01.img/..",
        "sdmc:/kitserver13/img/dt01.img/.",
        "sdmc:/kitserver13/img/dt01.img/",
        "sdmc:/kitserver13/../img/dt01.img/file.bin",
        "sdmc:/kitserver13//img/dt01.img/file.bin",
        "sdmc:/img/dt01.img/kitserver13",
        "sdmc:/kitserver13/img/.img/file.bin",
        "sdmc:/kitserver13/img/dt01.img.bak/file.bin",
        "sdmc:/kitserver13/img/dt01.img",
        "romfs:/kitserver13/img/dt01.img/file.bin",
    };
    for(unsigned i=0;i<sizeof(eligible)/sizeof(*eligible);i++)assert(horizon_dir_is_asset(eligible[i]));
    for(unsigned i=0;i<sizeof(ordinary)/sizeof(*ordinary);i++)assert(!horizon_dir_is_asset(ordinary[i]));
    horizon_dir_set_asset_scan(1);
    previous=timestamp_calls;unsigned paths=translation_calls,converted=conversion_calls;
    char filename[256];
    for(unsigned i=0;i<14258;i++){
        snprintf(filename,sizeof(filename),"sdmc:/kitserver13/Patch/img/dt00_e.img/unnamed_%u.bin",i);
        hint.file_size=(uint64_t)i*0x100000001ULL;
        assert(horizon_dir_entry_stat(filename,&hint,&st,0)==2);
        assert((uint64_t)st.st_size==hint.file_size && st.st_mode==(S_IFREG|0666));
        assert(!st.st_ctime && !st.st_mtime && !st.st_atime && errno==ERANGE);
    }
    assert(timestamp_calls==previous && translation_calls==paths && conversion_calls==converted);cases++;
    for(unsigned i=0;i<sizeof(ordinary)/sizeof(*ordinary);i++)
        assert(horizon_dir_entry_stat(ordinary[i],&hint,&st,0)!=2);
    hint.metadata=0;assert(horizon_dir_entry_stat(eligible[0],&hint,&st,0)==0);hint.metadata=1;
    hint.file_size=UINT64_MAX;assert(horizon_dir_entry_stat(eligible[0],&hint,&st,0)==0);hint.file_size=128;
    horizon_dir_set_asset_scan(0);
    previous=timestamp_calls;
    assert(horizon_dir_entry_stat(eligible[0],&hint,&st,0)==1 && timestamp_calls==previous+1);
    assert(st.st_mtime==(time_t)(timestamps.modified-25200));cases+=3;

    /* Quiet launch is free of timestamps, tracing and observer reservation. */
    unsigned t=horizon_dir_diag_begin(4);assert(!t);
    horizon_dir_diag_stage(t,3);horizon_dir_diag_end(t,1);horizon_dir_diag_tick();
    assert(!clock_calls && !traces);cases++;
    debug_enabled=1;unsigned slots[16];
    for(unsigned i=0;i<16;i++){slots[i]=horizon_dir_diag_begin(0x1c34+i);assert(slots[i]);}
    assert(!horizon_dir_diag_begin(17));
    horizon_dir_diag_stage(slots[0],4);fake_time+=60000000ULL;
    errno=ERANGE;horizon_dir_diag_tick();assert(errno==ERANGE);
    assert(strstr(trace,"phase=timestamp ms=6000") && strstr(trace,"active=16"));
    for(unsigned i=0;i<16;i++)horizon_dir_diag_end(slots[i],i?0:1);
    horizon_dir_diag_tick();assert(strstr(trace,"done=16 fast=1 fallback=15 active=0"));
    assert(horizon_dir_diag_costs[4].peak==60000000ULL);cases++;
    unsigned n=traces;horizon_dir_diag_tick();assert(n==traces);cases++;
    pthread_t threads[4];
    for(unsigned i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,observe_worker,NULL));
    for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
    assert(horizon_dir_diag_finished==2016 && horizon_dir_diag_fast==2001);
    for(unsigned i=0;i<16;i++)assert(!horizon_dir_diag_slots[i].claimed && !horizon_dir_diag_slots[i].phase);
    cases++;
    debug_enabled=0;n=traces;horizon_dir_diag_tick();assert(n==traces);cases++;
    printf("{\"passed\":true,\"cases\":%u,\"real_timestamps\":true,\"quiet_observer\":true,\"concurrent_queries\":2000,"
           "\"asset_entries_without_timestamp_ipc\":14258,\"policy_override\":true}\n",cases);
    return 0;
}
