/* LGPL-2.1-or-later. Validate the running process, not its NSP filename.
 * svcGetInfo ASLR region is the alias-code span; on Horizon its upper bound
 * identifies these address spaces. The 32-bit no-reserved layout has a zero
 * alias region. Values come from the kernel, never from launcher preferences. */
#ifndef FEXTENDO_LAUNCH_MEMORY_H
#define FEXTENDO_LAUNCH_MEMORY_H
#include <stdint.h>
#include <stdio.h>
enum fx_memory_mode { FX_MEMORY_UNKNOWN,FX_MEMORY_32_ALIAS,FX_MEMORY_32_NO_ALIAS,FX_MEMORY_36,FX_MEMORY_39,FX_MEMORY_42 };
struct fx_launch_memory {uint64_t base,size,alias,total;uint32_t base_rc,size_rc,alias_rc,total_rc;};
static int fx_memory_mode(const struct fx_launch_memory *m){
    if(m->base_rc||m->size_rc||m->alias_rc||!m->size||m->base>UINT64_MAX-m->size)return FX_MEMORY_UNKNOWN;
    uint64_t end=m->base+m->size;
    if(end==(1ull<<32))return m->alias?FX_MEMORY_32_ALIAS:FX_MEMORY_32_NO_ALIAS;
    if(end==(1ull<<36))return FX_MEMORY_36;
    if(end==(1ull<<39))return FX_MEMORY_39;
    if(end==(1ull<<42))return FX_MEMORY_42;
    return FX_MEMORY_UNKNOWN;
}
static const char *fx_memory_mode_name(int mode){
    switch(mode){
    case FX_MEMORY_32_ALIAS:return "32-bit with alias";
    case FX_MEMORY_32_NO_ALIAS:return "32-bit no-alias";
    case FX_MEMORY_36:return "36-bit";
    case FX_MEMORY_39:return "39-bit";
    case FX_MEMORY_42:return "42-bit";
    default:return "Unknown (could not verify)";
    }
}
#ifdef __SWITCH__
static struct fx_launch_memory fx_startup_memory;
static int fx_startup_memory_read;
static void fx_launch_memory_read(void){
    /* Process layout is immutable. Query once during launcher bootstrap and
     * reuse it for the pre-heap/preload guard and the launcher rejection. */
    if(fx_startup_memory_read)return;
    struct fx_launch_memory *m=&fx_startup_memory;
    m->base_rc=svcGetInfo(&m->base,InfoType_AslrRegionAddress,CUR_PROCESS_HANDLE,0);
    m->size_rc=svcGetInfo(&m->size,InfoType_AslrRegionSize,CUR_PROCESS_HANDLE,0);
    m->alias_rc=svcGetInfo(&m->alias,InfoType_AliasRegionSize,CUR_PROCESS_HANDLE,0);
    m->total_rc=svcGetInfo(&m->total,InfoType_TotalMemorySize,CUR_PROCESS_HANDLE,0);
    fx_startup_memory_read=1;
}
/* Used before libnx heap and applet/HID/VI mappings. No gameplay polling. */
int wine_nx_launch_memory_compatible(void){
    fx_launch_memory_read();
    return fx_memory_mode(&fx_startup_memory)==FX_MEMORY_32_NO_ALIAS;
}
static __attribute__((noinline,used)) int fx_launch_memory_validate(void){
    fx_launch_memory_read();
    struct fx_launch_memory *m=&fx_startup_memory;
    int mode=fx_memory_mode(m);if(mode==FX_MEMORY_32_NO_ALIAS)return 1;
    char message[512],details[1600];
    snprintf(message,sizeof(message),"Unsupported launch mode: %s.\nFEXTendo requires 32-bit no-alias.\nOpen PES13 using the supplied FEXTendo NSP on the HOME Menu.",fx_memory_mode_name(mode));
    snprintf(details,sizeof(details),"Install the FEXTendo NSP from github.com/Ibnuard/pes13_nx/releases.\n"
        "Launching the NRO directly from Homebrew Menu or a generic forwarder may use an incompatible memory layout.\n"
        "The NRO cannot change the address-space type of an already running process.\n\n"
        "ASLR base: 0x%llx\nASLR size: 0x%llx\nAlias size: 0x%llx\nMemory budget: %llu MiB\n"
        "Query results: %x / %x / %x / %x",
        (unsigned long long)m->base,(unsigned long long)m->size,(unsigned long long)m->alias,
        (unsigned long long)(m->total>>20),m->base_rc,m->size_rc,m->alias_rc,m->total_rc);
    /* A homebrew LibraryApplet need not be able to launch the system error
     * applet. Use its existing window and return normally to its own loader. */
    if(consoleInit(NULL)){
        printf("%s\n\n%s\n\nPress + or B to return.\n",message,details);
        PadState pad;padConfigureInput(1,HidNpadStyleSet_NpadStandard);padInitializeDefault(&pad);
        while(appletMainLoop()){
            padUpdate(&pad);if(padGetButtonsDown(&pad)&(HidNpadButton_Plus|HidNpadButton_B))break;
            consoleUpdate(NULL);svcSleepThread(20000000);
        }
        consoleExit(NULL);
    }
    return 0;
}
#endif
#endif
