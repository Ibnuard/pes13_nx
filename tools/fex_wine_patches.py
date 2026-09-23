"""FEX2-only Wine bootstrap and exception integration, with checked snapshots."""
from pathlib import Path
import hashlib
import json


def apply(work, project):
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
        if kind == 'native-source':
            # Runtime path isolation includes Wine's Unix filesystem/server paths.
            for path in [*(source / 'wine-nx-probe/source').glob('*.c'),
                         *(source / 'wine-nx-probe/source').glob('*.h'),
                         *(source / 'dlls/ntdll/unix').glob('*.c')]:
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
