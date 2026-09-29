"""Named dxvk-cs-only offload experiment on the short-trace baseline."""
def apply(read,replace,project):
    name='wine-nx-probe/source/thread_profile.c'
    anchor='static uintptr_t runtime_base, runtime_end;'
    replace(name,anchor,anchor+'\n#include "'+str(project/'src/runtime/fex_dxvk_core3.h')+'"')
    replace(name,'        registry[slot].handle = handle;',
            '        memset(&fex_dxvk_slots[slot],0,sizeof(fex_dxvk_slots[slot]));\n        registry[slot].handle = handle;')
    # Never let the 0-2 balancer move an offloaded or partially restored helper.
    replace(name,"        if (!thread->handle || thread->kind != 'w') continue;",
            "        if (!thread->handle || thread->kind != 'w' || fex_dxvk_slots[i].active) continue;")
    name='dlls/ntdll/unix/thread.c'
    replace(name,'static void set_native_thread_name( HANDLE handle, const UNICODE_STRING *name )\n{\n#ifdef linux',
'''extern void wine_nx_fex_dxvk_name(unsigned tid, const char *name);
extern int wine_nx_fex_dxvk_affinity(unsigned tid, uint64_t mask);
static int fex_dxvk_explicit_affinity(HANDLE handle, ULONG_PTR mask)
{
    THREAD_BASIC_INFORMATION info;
    if (!mask || NtQueryInformationThread(handle,ThreadBasicInformation,&info,sizeof(info),NULL) ||
        HandleToULong(info.ClientId.UniqueProcess)!=GetCurrentProcessId()) return 0;
    return wine_nx_fex_dxvk_affinity(HandleToULong(info.ClientId.UniqueThread),mask);
}
static void set_native_thread_name( HANDLE handle, const UNICODE_STRING *name )
{
#ifdef __SWITCH__
    THREAD_BASIC_INFORMATION info;
    char text[64];
    if (NtQueryInformationThread(handle,ThreadBasicInformation,&info,sizeof(info),NULL) ||
        HandleToULong(info.ClientId.UniqueProcess)!=GetCurrentProcessId()) return;
    unsigned count=name->Length/sizeof(WCHAR);
    if(count>=sizeof(text))count=sizeof(text)-1;
    for(unsigned i=0;i<count;i++)text[i]=name->Buffer[i]<128?(char)name->Buffer[i]:'?';
    text[count]=0;
    wine_nx_fex_dxvk_name(HandleToULong(info.ClientId.UniqueThread),text);
#elif defined(linux)''')
    replace(name,'        if (!status && is_current_thread_handle( handle )) horizon_pin_current_thread( req_aff );',
            '        if (!status && !fex_dxvk_explicit_affinity(handle,req_aff) && is_current_thread_handle( handle )) horizon_pin_current_thread( req_aff );')
    name='wine-nx-probe/source/runtime.c'
    anchor='    if (wine_nx_config_file_bool(RUNTIME_DIR "/no-balance.txt", 0)) wine_nx_balance_enabled = 0;'
    replace(name,anchor,
            '    extern void wine_nx_fex_dxvk_configure(int requested,int automatic_core3);\n'
            '    const int fex_dxvk_balance = wine_nx_config_file_bool(RUNTIME_DIR "/fex_dxvk_balance", 1);\n'
            '    const int fex_dxvk_legacy = wine_nx_config_file_bool(RUNTIME_DIR "/fex_dxvk_core3", 0);\n'
            '    wine_nx_fex_dxvk_configure(!guest_tests && !fex_dxvk_balance && fex_dxvk_legacy, wine_nx_fex_auto_core3);\n'
            '    log_line("[FEX3-DXVKPOLICY] v2 balance=%d legacy_core3=%d effective_offload=%d; balanced uses ordinary application worker placement and priority",\n'
            '             fex_dxvk_balance, fex_dxvk_legacy, !guest_tests && !fex_dxvk_balance && fex_dxvk_legacy);\n'+anchor)
    replace(name,'"pes13-fextendo-short-trace-v1"','"pes13-fextendo-dxvk-core3-v1"')
