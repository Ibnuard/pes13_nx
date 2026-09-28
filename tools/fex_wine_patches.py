"""Isolated FEX2/FEX3 Wine bootstrap and exception integration patches."""
from pathlib import Path
import hashlib
import json


def apply(work, project, integration=False, samecore_yield=False, runtime_fixes=False, diagnostic=False,
          resume_gate=False, stability=False, hang_audit=False, warm_audit=False, jit_latency=False, sleep_deadline=False,
          worker_cores=False, jit_log_queue=False, yield_burst=False, yield_adaptive=False, stable_balance=False, gap_audit=False, launcher=False,
          memory_audit=False, memory_budget_filter=False):
    if memory_budget_filter and not memory_audit:
        raise ValueError('Memory budget filter requires memory audit baseline')
    if memory_audit and not launcher:
        raise ValueError('Memory audit requires launcher baseline')
    if launcher and not gap_audit:
        raise ValueError('Launcher requires gap audit baseline')
    if gap_audit and not stable_balance:
        raise ValueError('Gap audit requires stable balance baseline')
    if stable_balance and (not yield_burst or yield_adaptive):
        raise ValueError('Stable balance requires yield burst and excludes adaptive yield')
    if yield_adaptive and not yield_burst:
        raise ValueError('Adaptive yield requires yield burst baseline')
    if yield_burst and (not jit_log_queue or not samecore_yield):
        raise ValueError('Yield burst requires JIT log queue and same-core yield baseline')
    if jit_log_queue and not worker_cores:
        raise ValueError('JIT log queue requires worker placement baseline')
    if worker_cores and not sleep_deadline:
        raise ValueError('Worker placement requires sleep deadline baseline')
    if sleep_deadline and not jit_latency:
        raise ValueError('Sleep deadline requires JIT latency baseline')
    if jit_latency and not warm_audit:
        raise ValueError('JIT latency requires warm audit')
    if warm_audit and not hang_audit:
        raise ValueError('warm audit requires hang audit')
    if hang_audit and (not stability or not integration):
        raise ValueError('hang audit requires the combined FEX3 stability runtime')
    if stability:
        if not integration:
            raise ValueError('stability requires the isolated FEX3 runtime')
        runtime_fixes = resume_gate = diagnostic = True
    if resume_gate and not integration:
        raise ValueError('resume gate requires the isolated FEX3 runtime')
    if resume_gate and runtime_fixes and not stability:
        raise ValueError('resume gate cannot combine with runtime fixes')
    if diagnostic and not integration:
        raise ValueError('diagnostic requires the isolated FEX3 runtime')
    if diagnostic and runtime_fixes and not stability:
        raise ValueError('diagnostic cannot combine with runtime fixes')
    if samecore_yield and not integration:
        raise ValueError('same-core yield requires the isolated FEX3 runtime')
    if runtime_fixes and not integration:
        raise ValueError('runtime fixes require the isolated FEX3 runtime')
    report = {}
    for kind in ('native-source', 'pe-source'):
        source = work / kind
        saved = json.loads((work / (kind + '.json')).read_text())['files']
        cache = work / (kind + '-originals')
        cache.mkdir(exist_ok=True)
        patched = {}

        def read(name):
            if name in patched:
                return patched[name]
            original = cache / name
            if not original.exists():
                data = (source / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != saved[name]:
                    raise RuntimeError(f'Unexpected snapshot modification: {source / name}')
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(data)
            patched[name] = original.read_text()
            return patched[name]

        def replace(name, old, new, count=1):
            data = read(name)
            if data.count(old) != count:
                raise RuntimeError(f'{kind}/{name}: expected {count} anchors, got {data.count(old)}: {old[:90]}')
            patched[name] = data.replace(old, new)

        name = 'dlls/wow64/syscall.c'
        replace(name, '            return L"winebox64.dll";',
                '            return L"winebox64.dll";\n'
                '        if (native_machine == IMAGE_FILE_MACHINE_ARM64 &&\n'
                '            __wine_switch_cpu_backend == 0x46455832u) return L"libwow64fex.dll";')
        if integration and kind == 'pe-source':
            name = 'dlls/ntdll/signal_arm64.c'
            replace(name, '    return pWow64SuspendLocalThread( thread, count );',
                    '    return pes13_fex_suspend_local_thread( thread, count );')
            replace(name, '/***********************************************************************\n *              RtlWow64SuspendThread (NTDLL.@)',
                    (project / 'src/runtime/fex_suspend_backoff.h').read_text() +
                    '\n/***********************************************************************\n *              RtlWow64SuspendThread (NTDLL.@)')
            name = 'dlls/ntdll/loader.c'
            replace(name, 'static RTL_RB_TREE base_address_index_tree;', r'''
static RTL_RB_TREE base_address_index_tree_storage;
/* The Horizon bootstrap and this PE loader own the same LDR entries. Share
 * the tree itself: copying its root once becomes stale after an insertion,
 * and inserting the same intrusive nodes into a second tree corrupts both. */
RTL_RB_TREE *wine_nx_pe_module_index = &base_address_index_tree_storage;
#define base_address_index_tree (*wine_nx_pe_module_index)
''')
            replace(name, '/******************************************************************\n *              LdrEnumerateLoadedModules (NTDLL.@)', r'''
/* Bounded bootstrap check, called through the native-to-PE ABI trampoline.
 * Check the real PE lookup and unwind table before any x86 execution. */
#ifdef __aarch64__
struct wine_nx_module_probe { void *pc, *base; };
NTSTATUS WINAPI wine_nx_validate_module_index(const struct wine_nx_module_probe *probes, ULONG count)
{
    ULONG i;
    if (!probes || count != 3) return STATUS_INVALID_PARAMETER;
    for (i = 0; i < count; ++i)
    {
        LDR_DATA_TABLE_ENTRY *module;
        ULONG_PTR base = 0;
        if (!probes[i].pc || LdrFindEntryForAddress(probes[i].pc, &module) ||
            module->DllBase != probes[i].base) return STATUS_DLL_NOT_FOUND;
        if (!RtlLookupFunctionEntry((ULONG_PTR)probes[i].pc, &base, NULL) ||
            base != (ULONG_PTR)probes[i].base) return STATUS_BAD_FUNCTION_TABLE;
    }
    return STATUS_SUCCESS;
}
#endif

/******************************************************************
 *              LdrEnumerateLoadedModules (NTDLL.@)''')
            name = 'dlls/ntdll/ntdll.spec'
            replace(name, '@ extern -private wine_nx_pe_hash_table',
                    '@ extern -private wine_nx_pe_hash_table\n'
                    '@ extern -private wine_nx_pe_module_index\n'
                    '@ stdcall -private -arch=arm64 wine_nx_validate_module_index(ptr long)')
        if kind == 'native-source':
            # Runtime path isolation includes Wine's Unix filesystem/server paths.
            integration_paths = ([*(source / 'dlls/ntdll').glob('*.c'),
                                  *(source / 'dlls/ntdll/unix').glob('*.h')]
                                 if integration else [])
            for path in [*(source / 'wine-nx-probe/source').glob('*.c'),
                         *(source / 'wine-nx-probe/source').glob('*.h'),
                         *(source / 'dlls/ntdll/unix').glob('*.c'), *integration_paths]:
                name = str(path.relative_to(source))
                if name not in saved:
                    continue
                original_path = cache / name
                original_text = (original_path if original_path.exists() else path).read_text()
                if 'switch/pes13-nx' in original_text:
                    patched[name] = read(name).replace('switch/pes13-nx', 'switch/pes13-fex2')

            name = 'dlls/ntdll/loader.c'
            replace(name, 'NTSTATUS wine_nx_loader_prepare_wow64( HMODULE *native_ntdll, void **initialize )',
                    '#include "wine_bridge.h"\n\nNTSTATUS wine_nx_loader_prepare_wow64( HMODULE *native_ntdll, void **initialize )')
            replace(name, 'L"wow64win.dll", L"winebox64.dll"', 'L"wow64win.dll", L"libwow64fex.dll"')
            replace(name, '        status = alloc_thread_tls();\n        for (i = 0; !status',
                    '        status = alloc_thread_tls();\n'
                    '        if (!status) status = pes13_fex_install_module(loaded[3]->ldr.DllBase);\n'
                    '        for (i = 0; !status')
            replace(name, '*cpu_backend = IMAGE_FILE_MACHINE_I386;', '*cpu_backend = PES13_WOW64_BACKEND_FEX;')
            replace(name, '[WOW64] selected winebox64.dll through native bootstrap',
                    '[FEX2] selected libwow64fex.dll through native bootstrap')

            name = 'dlls/ntdll/unix/horizon.c'
            data = read(name)
            begin = data.index('static void horizon_resume_exception( ThreadExceptionDump *ctx ) __attribute__')
            end = data.index('\n#endif', begin)
            patched[name] = data[:begin] + r'''
#include "wine_bridge.h"
static void pes13_fex_dump_context(const ThreadExceptionDump *dump, CONTEXT *context)
{
    unsigned int i;
    memset(context, 0, sizeof(*context));
    context->ContextFlags = CONTEXT_FULL | CONTEXT_ARM64_X18;
    for (i = 0; i < 29; ++i) context->X[i] = dump->cpu_gprs[i].x;
    context->Fp = dump->fp.x;
    context->Lr = dump->lr.x;
    context->Sp = dump->sp.x;
    context->Pc = dump->pc.x;
    context->Cpsr = dump->pstate;
    context->Fpcr = dump->pad[0];
    context->Fpsr = dump->pad[1];
    memcpy(context->V, dump->fpu_gprs, sizeof(context->V));
}

static void horizon_resume_exception(ThreadExceptionDump *dump) __attribute__((noreturn));
static void horizon_resume_exception(ThreadExceptionDump *dump)
{
    CONTEXT context;
    pes13_fex_dump_context(dump, &context);
    pes13_fex_restore_context(&context);
}

void horizon_continue_context(const CONTEXT *context)
{
    CONTEXT copy = *context;
    if (!(context->ContextFlags & (CONTEXT_ARM64_X18 & ~CONTEXT_ARM64)))
        copy.X18 = (uintptr_t)NtCurrentTeb();
    pes13_fex_restore_context(&copy);
}
''' + data[end:]
            replace(name, 'void __libnx_exception_handler( ThreadExceptionDump *ctx )',
                    'void pes13_fex_wine_exception_handler( ThreadExceptionDump *ctx )')
            replace(name, '    if (horizon_redirect_user_shared_data( ctx ))',
                    '    extern void pes13_fex_test_fault(void);\n'
                    '    if (ctx->pc.x == (uintptr_t)pes13_fex_test_fault)\n'
                    '    { ctx->pc.x += 4; horizon_resume_exception(ctx); }\n'
                    '    if (horizon_redirect_user_shared_data( ctx ))')
            replace(name, '    status = virtual_handle_fault( &rec, (void *)ctx->sp.x );', r'''
    /* Decode exception type before dispatch: an unaligned atomic is not an
     * ordinary access violation. Invalid FAR is never given to a VM handler. */
    {
        unsigned int ec = esr >> 26;
        if (((ec == 0x24 || ec == 0x25) && (esr & 0x3f) == 0x21) || ec == 0x22 || ec == 0x26)
            rec.ExceptionCode = STATUS_DATATYPE_MISALIGNMENT;
        else if (ec == 0x3c) rec.ExceptionCode = STATUS_BREAKPOINT;
        else if (ec != 0x20 && ec != 0x21 && ec != 0x24 && ec != 0x25)
            rec.ExceptionCode = STATUS_ILLEGAL_INSTRUCTION;
        if (rec.ExceptionCode != STATUS_ACCESS_VIOLATION) rec.NumberParameters = 0;
        status = rec.ExceptionCode;
        if (rec.ExceptionCode == STATUS_ACCESS_VIOLATION && !(esr & (1u << 10)))
            status = virtual_handle_fault(&rec, (void *)ctx->sp.x);
        if (status && !(rec.ExceptionCode == STATUS_ACCESS_VIOLATION && (esr & (1u << 10))))
        {
            CONTEXT context;
            pes13_fex_dump_context(ctx, &context);
            if (pes13_fex_dispatch_exception(&rec, &context)) pes13_fex_restore_context(&context);
        }
    }''')

            # FEX's explicitly native helpers use SKIP_LOADER_INIT. A native
            # entry in a WOW64 process must not be decoded as x86 guest bytes.
            name = 'dlls/ntdll/unix/signal_arm64.c'
            replace(name, '    if (get_wow_teb( teb ))\n    {\n        if (wine_nx_wow64_thread_start)',
                    '    if (get_wow_teb( teb ) && !teb->SkipLoaderInit)\n    {\n        if (wine_nx_wow64_thread_start)')

            name = 'wine-nx-probe/source/runtime.c'
            replace(name, '#include "pes13_controller.h"', '#include "pes13_controller.h"\n#include "wine_bridge.h"')
            replace(name, '#define DEFAULT_TARGET WINE_DRIVE_C "/PES13/pes2013.exe"',
                    '#define DEFAULT_TARGET WINE_DRIVE_C "/fex-smoke.exe"')
            replace(name, '#define WINE_NX_RUNTIME_BUILD "nx-wow64-console-11"',
                    '#define WINE_NX_RUNTIME_BUILD "pes13-fex2-x86-bringup"')
            # Select the generic WOW64 bootstrap without linking a Box64 engine.
            data = read(name)
            patched[name] = data.replace('#ifdef WINE_NX_BOX64_INTERPRETER', '#if defined(WINE_NX_FEX) || defined(WINE_NX_BOX64_INTERPRETER)')
            replace(name, 'RUNTIME_DIR "/pes13-nx.log"', 'RUNTIME_DIR "/fex-runtime.log"')
            replace(name, '    wine_nx_runtime_verbose = read_bool_file( RUNTIME_DIR "/verbose.txt" );',
                    '    wine_nx_runtime_trace("[FEX2] context preflight before Wine startup");\n'
                    '    if (!pes13_fex_context_preflight()) park_forever();\n'
                    '    if (setenv("WINEPREFIX", "/switch/pes13-fex2", 1))\n'
                    '    { wine_nx_runtime_trace("[FEX2] environment setup failed"); park_forever(); }\n'
                    '    wine_nx_runtime_verbose = 0;')
            replace(name, 'if (!log_flusher_running || log_line_is_urgent( line ))',
                    'if (!log_flusher_running || !strncmp(line, "[FEX", 4) || log_line_is_urgent( line ))')
            if not integration:
                start = read(name).index('    {\n        extern int wine_nx_pes13_preload_report(void);')
                end = read(name).index('    log_line( "[SDCACHE]', start)
                patched[name] = patched[name][:start] + patched[name][end:]
            # No display/game/controller activity required for a console guest.
            replace(name, '    wine_nx_pes13_registry_enabled =\n'
                    '        !strcmp(target, "sdmc:/switch/pes13-fex2/drive_c/PES13/pes2013.exe") ||\n'
                    '        !strcmp(target, "sdmc:/switch/pes13-fex2/drive_c/PES13/settings.exe");',
                    '    wine_nx_pes13_registry_enabled = 0;')
            replace(name, '    if (read_bool_file( RUNTIME_DIR "/framebuffer.txt" )) wine_nx_compositor_mode = 0;',
                    '    wine_nx_compositor_mode = 0;')
            name = 'wine-nx-probe/CMakeLists.txt'
            replace(name, 'project(wine_nx_probe LANGUAGES C CXX ASM)',
                    'project(wine_nx_probe LANGUAGES C CXX ASM)\n'
                    'include_directories("${PES13_FEX_DIR}")\nadd_compile_definitions(WINE_NX_FEX=1)')
            replace(name, 'target_sources(wine-nx-runtime PRIVATE source/pes13_preload.c)\n'
                    'target_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=appletInitialize)',
                    'target_sources(wine-nx-runtime PRIVATE\n'
                    ' "${PES13_FEX_DIR}/horizon_jit.c" "${PES13_FEX_DIR}/wine_bridge.c"\n'
                    ' "${PES13_FEX_DIR}/exception_entry.S" "${PES13_FEX_DIR}/context_test.S"\n'
                    ' "${PES13_LIBNX_EXCEPTION_OBJECT}")')

            if integration:
                from fex_reservation_patches import apply as apply_reservation_patches
                from fex_thread_patches import apply as apply_thread_patches
                from fex_fd_patches import apply as apply_fd_patches
                apply_reservation_patches(replace)
                apply_thread_patches(read, replace)
                apply_fd_patches(read, replace)
                # PE and native now mutate a shared module index. The native
                # bootstrap's old unbalanced insert / no-op remove shims cannot
                # supply the red-black invariants expected by PE Wine. Reuse
                # this snapshot's Wine implementation, including its helpers.
                rtl = read('dlls/ntdll/rtl.c')
                start = rtl.index('static RTL_BALANCED_NODE *rtl_node_parent(')
                end = rtl.index('/***********************************************************************\n *           RtlInitializeGenericTableAvl', start)
                name = 'wine-nx-probe/source/ntdll_pe_compat.c'
                data = read(name)
                first = data.index('void WINAPI RtlRbInsertNodeEx(')
                last = data.index('ULONG WINAPI RtlRandom(', first)
                patched[name] = data[:first] + rtl[start:end] + data[last:]
                replace(name, '#include "wine/exception.h"',
                        '#include "wine/exception.h"\n#include "wine/debug.h"\n'
                        'WINE_DEFAULT_DEBUG_CHANNEL(ntdll);')
                name = 'dlls/ntdll/loader.c'
                replace(name, '        if (!status) status = pes13_fex_install_module(loaded[3]->ldr.DllBase);',
                        '        if (!status) status = pes13_fex_install_module(loaded[3]->ldr.DllBase);\n'
                        '        if (!status) status = pes13_fex_install_dispatcher(loaded[0]->ldr.DllBase,\n'
                        '            &base_address_index_tree, loaded[3]->ldr.DllBase, loaded[1]->ldr.DllBase);')
                name = 'dlls/ntdll/unix/signal_arm64.c'
                replace(name, '''NTSTATUS call_user_exception_dispatcher( EXCEPTION_RECORD *rec, CONTEXT *context )
{
    (void)rec;
    (void)context;
    return STATUS_NOT_IMPLEMENTED;
}''', r'''
/* Match the native ARM64 ntdll exception frame, including CONTEXT_EX. The
 * Horizon syscall bridge uses the caller stack, so resume directly instead
 * of setting a Linux syscall_frame. The PE dispatcher invokes Wine's normal
 * Wow64PrepareForException / Wow64PassExceptionToGuest path. */
#include "wine_bridge.h"
struct horizon_exc_stack_layout
{
    CONTEXT context;
    CONTEXT_EX context_ex;
    EXCEPTION_RECORD rec;
    ULONG64 align, sp, pc, redzone[2];
};
C_ASSERT(offsetof(struct horizon_exc_stack_layout, rec) == 0x3b0);
C_ASSERT(sizeof(struct horizon_exc_stack_layout) == 0x470);

NTSTATUS call_user_exception_dispatcher(EXCEPTION_RECORD *rec, CONTEXT *context)
{
    struct horizon_exc_stack_layout *stack;
    CONTEXT next;
    unsigned int trace = pes13_fex_begin_guest_dispatch();
    pes13_fex_trace_guest_dispatch(trace, "enter", rec, context);
    if (!rec || !context || !pKiUserExceptionDispatcher || !context->Sp)
        return STATUS_INVALID_PARAMETER;
    pes13_fex_fault_stage(5, context->Pc, (uintptr_t)rec->ExceptionAddress, rec->ExceptionCode);
    next = *context;
    stack = virtual_setup_exception((void *)(context->Sp & ~15ull), sizeof(*stack), rec);
    if (!stack) return STATUS_STACK_OVERFLOW;
    pes13_fex_trace_guest_dispatch(trace, "stack-ready", rec, context);
    memmove(&stack->context, context, sizeof(*context));
    memmove(&stack->rec, rec, sizeof(*rec));
    /* Same empty-XSTATE layout as Wine's ARM64 signal path. */
    memset(&stack->context_ex, 0, sizeof(stack->context_ex));
    stack->context_ex.Legacy.Length = sizeof(CONTEXT);
    stack->context_ex.Legacy.Offset = -(LONG)sizeof(CONTEXT);
    stack->context_ex.XState.Length = 0;
    stack->context_ex.XState.Offset = (BYTE *)stack->redzone - (BYTE *)&stack->context_ex;
    stack->context_ex.All.Length = sizeof(CONTEXT) + stack->context_ex.XState.Offset;
    stack->context_ex.All.Offset = -(LONG)sizeof(CONTEXT);
    stack->align = 0;
    stack->sp = context->Sp;
    stack->pc = context->Pc;
    next.Pc = (ULONG_PTR)pKiUserExceptionDispatcher;
    next.Sp = (ULONG_PTR)stack;
    next.X18 = (ULONG_PTR)NtCurrentTeb();
    next.ContextFlags |= CONTEXT_FULL | CONTEXT_ARM64_X18;
    pes13_fex_trace_guest_dispatch(trace, "continue-dispatcher", rec, &next);
    pes13_fex_fault_stage(6, next.Pc, (uintptr_t)rec->ExceptionAddress, rec->ExceptionCode);
    return signal_set_full_context(&next);
}''')
                name = 'dlls/ntdll/unix/horizon.c'
                # The first team-selection freeze follows failed FEX heap
                # commits, but Horizon's detailed HMAP errors are hidden when
                # production disables the verbose trace. Emit only a bounded
                # failure path to the existing runtime log; never reopen an SD
                # file for every successful mapping or protection change.
                replace(name, 'static int set_code_memory_perm( void *addr, void *source, size_t size, int prot, BOOL source_accessible )', r'''
static void pes13_fex_hmap_failure( const char *fmt, ... )
{
    static LONG failures;
    char detail[224], line[256];
    __builtin_va_list args;
    if (__atomic_add_fetch( &failures, 1, __ATOMIC_RELAXED ) > 24) return;
    __builtin_va_start( args, fmt );
    vsnprintf( detail, sizeof(detail), fmt, args );
    __builtin_va_end( args );
    snprintf( line, sizeof(line), "[FEX3-HMAP] %s", detail );
    wine_nx_runtime_trace( line );
}

static int set_code_memory_perm( void *addr, void *source, size_t size, int prot, BOOL source_accessible )''')
                for failure in (
                    'set_perm failed', 'map_code failed', 'create_backing failed',
                    'reserve_target failed', 'map_backing failed',
                    'split_reservation failed', 'commit map_backing failed',
                ):
                    replace(name, f'horizon_trace( "[HMAP] {failure}',
                            f'pes13_fex_hmap_failure( "[HMAP] {failure}')
                replace(name, '            errno = ENOMEM;\n            return -1;\n        }\n\n        mapping_start = mapping->addr;',
                        '            errno = ENOMEM;\n'
                        '            pes13_fex_hmap_failure( "[HMAP] no mapping for commit range=%p/0x%lx",\n'
                        '                                     start, (unsigned long)(end - start) );\n'
                        '            return -1;\n        }\n\n        mapping_start = mapping->addr;')
                # The splash-to-intro run fails while replacing a 60 KiB
                # mapping. Preserve the exact Horizon result and source alias
                # for the next device run; errno=EINVAL alone loses both.
                replace(name,
                        '        WARN( "svcUnmapProcessCodeMemory(%p, %p, %zu) failed %#x.\\n", addr, source, size, rc );',
                        '        {\n'
                        '            static LONG failures;\n'
                        '            if (__atomic_add_fetch( &failures, 1, __ATOMIC_RELAXED ) <= 16)\n'
                        '                horizon_trace( "[FEX3-HMAP] unmap failed addr=%p source=%p size=0x%lx rc=0x%x",\n'
                        '                               addr, source, (unsigned long)size, rc );\n'
                        '        }\n'
                        '        WARN( "svcUnmapProcessCodeMemory(%p, %p, %zu) failed %#x.\\n", addr, source, size, rc );')
                replace(name, '            status = virtual_handle_fault(&rec, (void *)ctx->sp.x);',
                        '        {\n'
                        '            pes13_fex_fault_stage(1, ctx->pc.x, ctx->far.x, rec.ExceptionCode);\n'
                        '            status = virtual_handle_fault(&rec, (void *)ctx->sp.x);\n'
                        '            pes13_fex_fault_stage(2, ctx->pc.x, ctx->far.x, status);\n'
                        '        }')
                replace(name, '{ ctx->pc.x += 4; horizon_resume_exception(ctx); }',
                        '{ pes13_fex_context_fault_barrier(); ctx->pc.x += 4; horizon_resume_exception(ctx); }')
                name = 'dlls/ntdll/unix/sync.c'
                read(name)  # Also restore the original when leaving the experiment.
                if samecore_yield:
                    # The observed FEX run reaches >65k NtDelayExecution calls/s.
                    # Preserve Sleep(0)'s yield while avoiding forced migration.
                    replace(name, '    svcSleepThread( -1 );  /* YieldType_WithCoreMigration */',
                            '    svcSleepThread( 0 );  /* YieldType_WithoutCoreMigration: FEX Sleep(0) */')
                name = 'dlls/ntdll/unix/process.c'
                replace(name, '            snprintf( buf, sizeof(buf), "[EXIT] NtTerminateProcess(self) exit_code=0x%08x", (unsigned)exit_code );',
                        '            extern void pes13_fex_dump_fault_stages(void);\n'
                        '            pes13_fex_dump_fault_stages();\n'
                        '            snprintf( buf, sizeof(buf), "[EXIT] NtTerminateProcess(self) exit_code=0x%08x", (unsigned)exit_code );')
                name = 'wine-nx-probe/CMakeLists.txt'
                replace(name, 'add_compile_definitions(WINE_NX_FEX=1)',
                        'add_compile_definitions(WINE_NX_FEX=1 PES13_FEX_ISOLATED_EXCEPTIONS=1)')
                replace(name, ' "${PES13_LIBNX_EXCEPTION_OBJECT}")',
                        ' "${PES13_FEX_DIR}/exception_isolated.S" source/pes13_preload.c)\n'
                        'target_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=appletInitialize)')
                name = 'wine-nx-probe/source/runtime.c'
                from perf34_patches import _replace_runtime_flags
                patched[name] = _replace_runtime_flags(read(name), project)
                replace(name, '#define DEFAULT_TARGET WINE_DRIVE_C "/fex-smoke.exe"',
                        '#define DEFAULT_TARGET WINE_DRIVE_C "/PES13/pes2013.exe"')
                replace(name, '"pes13-fex2-x86-bringup"', '"pes13-fex3-timing-audit"')
                replace(name, '    wine_nx_runtime_trace("[FEX2] context preflight before Wine startup");',
                        '    const int guest_tests = wine_nx_config_file_bool(RUNTIME_DIR "/run-guest-tests.txt", 1);\n'
                        '    const unsigned fex_profile = pes13_fex_select_performance_profile(guest_tests,\n'
                        '        wine_nx_config_file_bool(RUNTIME_DIR "/fex-fast.txt", 1),\n'
                        '        wine_nx_config_file_bool(RUNTIME_DIR "/fex-fastest.txt", 0),\n'
                        '        wine_nx_config_file_bool(RUNTIME_DIR "/fex-relaxed-vectors.txt", 0));\n'
                        '    pes13_fex_set_performance_profile(fex_profile);\n'
                        '    if (guest_tests) snprintf(target, sizeof(target), "%s/fex-stress.exe", WINE_DRIVE_C);\n'
                        '    wine_nx_runtime_trace("[FEX3-MEM] v1 reserved-range recovery and self-thread cleanup query");\n'
                        '    wine_nx_runtime_trace("[FEX3-FD] v1 startup descriptors matched by original fd; keyed wakeups");\n'
                        '    wine_nx_runtime_trace("[FEX3-SUSPEND] Box64-style status passthrough; no injected 1ms delay");\n'
                        '    wine_nx_runtime_trace("[FEX3] isolated exception context preflight");' +
                        ('\n    wine_nx_runtime_trace("[FEX3-YIELD] same-core Sleep(0) experiment");'
                         if samecore_yield else ''))
                replace(name, '    if (!pes13_fex_context_preflight()) park_forever();',
                        '    if (!pes13_fex_context_preflight()) park_forever();\n'
                        '    if (guest_tests && !pes13_fex_fault_stress()) park_forever();')
                replace(name, 'static void runtime_report_interpreter(void)\n{',
                        'static void runtime_report_interpreter(void)\n{\n'
                        '    pes13_fex_report_heap();')
                replace(name, '    wine_nx_pes13_registry_enabled = 0;',
                        '    wine_nx_pes13_registry_enabled = !guest_tests;')
                # Retain the unified INI instead of reintroducing boolean files.
                # FEX2's console default also matches the tested PES DXVK path.
                replace(name, '    log_line( "[PES13-BOOT] single NRO; launching %s", target );',
                        '    log_line("[FEX3] mode=%s; one NRO; target=%s", guest_tests ? "guest-stress" : "PES13", target);')
                # Production previously waited two minutes before emitting
                # its first progress line. During the first 120 seconds, use
                # the existing second-call gate to emit a bounded line every
                # ten seconds, then restore the production cadence.
                replace(name, '        runtime_tick_std_streams();\n'
                        '        ++ticks;\n'
                        '        if ((!wine_nx_production && ticks % 25 == 0) ||\n'
                        '            (wine_nx_production && ticks % 300 == 0)) runtime_report_interpreter();',
                        '        ++ticks;\n'
                        '        if (wine_nx_production && ticks <= 600 && ticks % 25 == 0)\n'
                        '        {\n'
                        '            extern unsigned int wine_nx_vk_presents __attribute__((weak));\n'
                        '            unsigned int presents = &wine_nx_vk_presents\n'
                        '                ? __atomic_load_n( &wine_nx_vk_presents, __ATOMIC_RELAXED ) : 0;\n'
                        '            pthread_mutex_lock( &log_mutex );\n'
                        '            fprintf( log_file, "[FEX3-BOOT] %us vk_presents=%u fb_frames=%u\\n",\n'
                        '                     ticks / 5, presents,\n'
                        '                     __atomic_load_n( &wine_nx_fb_frames, __ATOMIC_RELAXED ) );\n'
                        '            fflush( log_file );\n'
                        '            pthread_mutex_unlock( &log_mutex );\n'
                        '        }\n'
                        '        runtime_tick_std_streams();\n'
                        '        if ((!wine_nx_production && ticks % 25 == 0) ||\n'
                        '            (wine_nx_production && (ticks <= 600 ? ticks % 25 == 0 : ticks % 300 == 0)))\n'
                        '            runtime_report_interpreter();')
                # The latest PES log activates an unidentified top-level
                # popup just before blackscreen. Record its bounded title,
                # class and owner without enabling Wine's per-message trace.
                name = 'dlls/win32u/window.c'
                replace(name, '    if (!(style & WS_CHILD))\n'
                        '        nx_window_trace( "[NXWIN] thread %04x shows hwnd %p with %d (style %#x, visible %d%s)",\n'
                        '                         (int)GetCurrentThreadId(), hwnd, cmd, (int)style, was_visible,\n'
                        '                         is_iconic( hwnd ) ? ", minimized" : "" );',
                        '    if (!(style & WS_CHILD))\n'
                        '    {\n'
                        '        WCHAR title[96] = {0}, class_name[64] = {0};\n'
                        '        UNICODE_STRING cls = {0, sizeof(class_name), class_name};\n'
                        '        NtUserInternalGetWindowText( hwnd, title, ARRAY_SIZE(title) );\n'
                        '        NtUserGetClassName( hwnd, FALSE, &cls );\n'
                        '        nx_window_trace( "[NXWIN] thread %04x shows hwnd %p with %d (style %#x, visible %d%s) owner=%p class=%s title=%s",\n'
                        '                         (int)GetCurrentThreadId(), hwnd, cmd, (int)style, was_visible,\n'
                        '                         is_iconic( hwnd ) ? ", minimized" : "",\n'
                        '                         get_window_relative( hwnd, GW_OWNER ),\n'
                        '                         debugstr_w( class_name ), debugstr_w( title ) );\n'
                        '    }')
                from fex_stall_patches import apply as apply_stall
                apply_stall(read, replace, project)
                from fex_self_suspend_patches import apply as apply_self_suspend
                apply_self_suspend(read, replace, project)
                from fex_frame_patches import apply as apply_frame
                apply_frame(read, replace, project)
                from fex_pipeline_patches import apply as apply_pipeline
                apply_pipeline(read, replace, project)
                from fex_sync_patches import apply as apply_sync
                apply_sync(read, replace, project)
                if resume_gate:
                    from fex_resume_patches import apply as apply_resume
                    apply_resume(read, replace, project)
                from fex_game_timing_patches import apply as apply_game_timing
                apply_game_timing(read, replace, project)
                if diagnostic:
                    name = 'wine-nx-probe/source/runtime.c'
                    replace(name, 'static void *log_flusher( void *arg )',
                            (project / 'src/runtime/fex_event_runtime.h').read_text() +
                            '\nstatic void *log_flusher( void *arg )')
                    replace(name, '        if (ticks % 25 == 0) fex_game_timing_report();',
                            '        if (ticks % 25 == 0) fex_game_timing_report();\n'
                            '        if (ticks % 5 == 0) fex_event_report(ticks / 5);')
                    replace(name, '"pes13-fex3-timing-audit"', '"pes13-fex3-event-diagnostic"')
                if runtime_fixes:
                    from fex_cache_patches import apply as apply_cache
                    from fex_runtime_fixes import apply as apply_runtime_fixes
                    apply_cache(read, replace, project)
                    apply_runtime_fixes(read, replace, project)
                    replace('wine-nx-probe/source/runtime.c',
                            '"pes13-fex3-event-diagnostic"' if diagnostic else '"pes13-fex3-timing-audit"',
                            '"pes13-fex3-stability-540p"' if stability else '"pes13-fex3-runtime-fixes"')
                if hang_audit:
                    from fex_hang_patches import apply as apply_hang
                    apply_hang(read, replace, project)
                if warm_audit:
                    from fex_warm_patches import apply as apply_warm
                    apply_warm(read, replace, project)
                if jit_latency:
                    from fex_jit_latency_patches import apply as apply_jit_latency
                    apply_jit_latency(read, replace, project)
                if sleep_deadline:
                    from fex_sleep_patches import apply as apply_sleep
                    apply_sleep(read, replace, project)
                if worker_cores:
                    from fex_worker_core_patches import apply as apply_worker_cores
                    apply_worker_cores(read, replace, project)
                if jit_log_queue:
                    from fex_jit_log_patches import apply as apply_jit_log_queue
                    apply_jit_log_queue(read, replace, project)
                if yield_burst:
                    from fex_yield_burst_patches import apply as apply_yield_burst
                    apply_yield_burst(read, replace, project)
                if yield_adaptive:
                    from fex_yield_adaptive_patches import apply as apply_yield_adaptive
                    apply_yield_adaptive(read, replace, project)
                if stable_balance:
                    from fex_balance_stable_patches import apply as apply_stable_balance
                    apply_stable_balance(read, replace, project)
                if gap_audit:
                    from fex_gap_probe_patches import apply as apply_gap_audit
                    apply_gap_audit(read, replace, project)
                if launcher:
                    from fextendo_launcher_patches import apply as apply_launcher
                    apply_launcher(read, replace, project)
                if memory_audit:
                    from fex_memory_probe_patches import apply as apply_memory_audit
                    apply_memory_audit(read, replace, project)
                if memory_budget_filter:
                    from fex_memory_budget_patches import apply as apply_memory_budget_filter
                    apply_memory_budget_filter(read, replace, project)
                for key in list(patched):
                    patched[key] = patched[key].replace('switch/pes13-fex2', 'switch/pes13-fex')

        state_file = work / (kind + '-patches.json')
        previous = json.loads(state_file.read_text()) if state_file.exists() else {}
        for name, data in patched.items():
            current = (source / name).read_bytes()
            digest = hashlib.sha256(current).hexdigest()
            if digest not in (saved[name], previous.get(name), hashlib.sha256(data.encode()).hexdigest()):
                raise RuntimeError(f'Refusing unexpected changes in {source / name}')
        for name, data in patched.items():
            if (source / name).read_text() != data:
                (source / name).write_text(data)
        hashes = {name: hashlib.sha256(data.encode()).hexdigest() for name, data in patched.items()}
        state_file.write_text(json.dumps(hashes, indent=2) + '\n')
        report[kind] = hashes
    return report
