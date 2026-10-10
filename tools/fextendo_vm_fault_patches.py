"""Report unresolved Wine/Horizon page permissions in Debug launch only.

Keep the fault result and page protections unchanged. This distinguishes a
missing/readonly guest mapping from a writable guest page denied by Horizon.
"""


def apply(source):
    name = 'dlls/ntdll/unix/horizon.c'
    path = source / name
    data = path.read_text()
    anchor = '/* Weak fallback definitions so smoke binaries (which don\'t link runtime.c\n'
    assert data.count(anchor) == 1, name
    helper = '''/* Called only for unresolved VM faults, after virtual_mutex is released.
 * Observe permissions; never grant access or skip the faulting instruction. */
void horizon_debug_vm_fault(void *address, unsigned vprot, unsigned kind, unsigned status, void *pc)
{
    extern int wine_nx_launch_debug_active(void);
    static u64 seen[32];
    u64 key, expected;
    unsigned slot;
    MemoryInfo info = {0};
    u32 page_info = 0;
    Result rc;
    if (!wine_nx_launch_debug_active()) return;
    /* FEX's prediction-stack guard can raise the same recoverable fault many
     * times before a real guest failure. Deduplicate by page/protection/kind,
     * not by PC: different blocks can hit that same guard. Claim at most one
     * fixed slot per distinct event; no allocation, locks or spin waiting in
     * the exception path. Page-offset bits encode the remaining fields. */
    key = ((u64)address & ~(u64)0xfff) | ((u64)(vprot & 0xff) << 4) |
          ((u64)(kind == 8 ? 2 : kind == 1 ? 1 : 0) << 2) |
          ((u64)(status == 0xc0000006) << 1) | 1;
    for (slot = 0; slot < 32; slot++)
    {
        expected = __atomic_load_n(&seen[slot], __ATOMIC_RELAXED);
        if (expected == key) return;
        if (!expected && __atomic_compare_exchange_n(&seen[slot], &expected, key, 0,
                                                     __ATOMIC_RELAXED, __ATOMIC_RELAXED)) break;
        if (expected == key) return;
    }
    if (slot == 32) return;
    rc = svcQueryMemory(&info, &page_info, (u64)address);
    horizon_trace("[VM-FAULT] v2 pc=%p addr=%p kind=%u status=%08x wine_vprot=%02x "
                  "query_rc=%x native_base=%p size=%lx type=%x perm=%x",
                  pc, address, kind, status, vprot, rc, (void *)info.addr,
                  (unsigned long)info.size, info.type, info.perm);
}

/* A bounded history of protections requested for the main guest image.
 * Includes FEX's native MTRACK calls as well as WOW64 app requests: caller
 * addresses distinguish the two in a device log. Never changes protections. */
void horizon_debug_vm_protect(void *address, size_t size, unsigned old_prot,
                              unsigned new_prot, unsigned status, void *caller)
{
    extern int wine_nx_launch_debug_active(void);
    static unsigned reports;
    unsigned slot;
    MemoryInfo info = {0};
    u32 page_info = 0;
    Result rc;
    if (!wine_nx_launch_debug_active()) return;
    slot = __atomic_load_n(&reports, __ATOMIC_RELAXED);
    do
    {
        if (slot >= 64) return;
    } while (!__atomic_compare_exchange_n(&reports, &slot, slot + 1, 0,
                                          __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    rc = svcQueryMemory(&info, &page_info, (u64)address);
    horizon_trace("[VM-PROTECT] v1 base=%p size=%lx old=%x new=%x status=%08x "
                  "caller=%p query_rc=%x native_base=%p native_size=%lx perm=%x",
                  address, (unsigned long)size, old_prot, new_prot, status, caller,
                  rc, (void *)info.addr, (unsigned long)info.size, info.perm);
}

'''
    path.write_text(data.replace(anchor, helper + anchor))

    name = 'dlls/ntdll/unix/virtual.c'
    path = source / name
    data = path.read_text()
    anchor = '#define mprotect horizon_mprotect'
    assert data.count(anchor) == 1, name
    data = data.replace(anchor, anchor + '\nextern void horizon_debug_vm_fault(void *, unsigned, unsigned, unsigned, void *);\n'
                        'extern void horizon_debug_vm_protect(void *, size_t, unsigned, unsigned, unsigned, void *);')
    anchor = '''    mutex_unlock( &virtual_mutex );
    rec->ExceptionCode = ret;
    return ret;
}'''
    assert data.count(anchor) == 1, name
    data = data.replace(anchor, '''    mutex_unlock( &virtual_mutex );
#ifdef __SWITCH__
    if (ret == STATUS_ACCESS_VIOLATION || ret == STATUS_IN_PAGE_ERROR)
        horizon_debug_vm_fault(addr, vprot, err, ret, rec->ExceptionAddress);
#endif
    rec->ExceptionCode = ret;
    return ret;
}''')
    # Restrict protection history to the main image, using the existing view
    # while the VM lock protects it. Do all logging after releasing that lock.
    begin = data.index('NTSTATUS WINAPI NtProtectVirtualMemory(')
    end = data.index('\n}\n', begin) + 3
    function = data[begin:end]
    assert function.count('    DWORD old;') == 1
    function = function.replace('    DWORD old;',
                                '    DWORD old = 0;\n#ifdef __SWITCH__\n'
                                '    BOOL horizon_trace_image = FALSE;\n#endif')
    anchor = '    if ((view = find_view( base, size )))\n    {'
    assert function.count(anchor) == 1
    function = function.replace(anchor, anchor + '\n#ifdef __SWITCH__\n'
        '        horizon_trace_image = (view->protect & SEC_IMAGE) &&\n'
        '            NtCurrentTeb()->Peb && view->base == NtCurrentTeb()->Peb->ImageBaseAddress;\n#endif')
    anchor = '    server_leave_uninterrupted_section( &virtual_mutex, &sigset );'
    assert function.count(anchor) == 1
    function = function.replace(anchor, anchor + '\n#ifdef __SWITCH__\n'
        '    if (horizon_trace_image)\n'
        '        horizon_debug_vm_protect(base, size, old, new_prot, status, __builtin_return_address(0));\n#endif')
    data = data[:begin] + function + data[end:]
    path.write_text(data)
    return {'dlls/ntdll/unix/horizon.c', 'dlls/ntdll/unix/virtual.c'}
