/* SPDX-License-Identifier: MIT */
#include <switch.h>
#include <stdio.h>
#include <string.h>
#include "ntstatus.h"
#define WIN32_NO_STATUS
#include "windef.h"
#include "winbase.h"
#include "winternl.h"
#include "wine_bridge.h"

C_ASSERT(offsetof(CONTEXT, X) == 8);
C_ASSERT(offsetof(CONTEXT, Fp) == 240);
C_ASSERT(offsetof(CONTEXT, Lr) == 248);
C_ASSERT(offsetof(CONTEXT, Sp) == 256);
C_ASSERT(offsetof(CONTEXT, Pc) == 264);
C_ASSERT(offsetof(CONTEXT, V) == 272);
C_ASSERT(offsetof(CONTEXT, Fpcr) == 784);
C_ASSERT(offsetof(CONTEXT, Fpsr) == 788);
C_ASSERT(offsetof(ThreadExceptionFrameA64, elr_el1) == 88);
C_ASSERT(offsetof(ThreadExceptionFrameA64, pstate) == 96);
C_ASSERT(offsetof(ThreadExceptionDump, pad) == 4);
C_ASSERT(offsetof(TEB, WowTebOffset) == 0x180c); /* FEX GetWowTEB contract */

extern void wine_nx_runtime_trace(const char *line);
static int (*handle_exception)(EXCEPTION_POINTERS *);

NTSTATUS pes13_fex_install_module(HMODULE module)
{
    int (*install)(const struct pes13_fex_host *);
    int (*ready)(void);
    install = (void *)RtlFindExportedRoutineByName(module, "PES13FexSetHost");
    ready = (void *)RtlFindExportedRoutineByName(module, "PES13FexHostReady");
    handle_exception = (void *)RtlFindExportedRoutineByName(module, "PES13FexHandleException");
    if (!install || !ready || !handle_exception) return STATUS_PROCEDURE_NOT_FOUND;
    pes13_fex_set_logger(wine_nx_runtime_trace);
    if (!install(pes13_fex_native_host()) || !ready()) return STATUS_REVISION_MISMATCH;
    wine_nx_runtime_trace("[FEX2] host ABI and exception bridge installed before CPU init");
    return STATUS_SUCCESS;
}

int pes13_fex_dispatch_exception(EXCEPTION_RECORD *record, CONTEXT *context)
{
    EXCEPTION_POINTERS pointers = {record, context};
    return handle_exception && handle_exception(&pointers);
}

extern void pes13_fex_test_restore(CONTEXT *requested, CONTEXT *observed);

int pes13_fex_context_preflight(void)
{
    CONTEXT expected = {0}, observed = {0};
    unsigned int i;
    expected.ContextFlags = CONTEXT_FULL | CONTEXT_ARM64_X18;
    for (i = 0; i < 31; ++i) expected.X[i] = 0x1020304000000000ull + i;
    expected.X[18] = (uintptr_t)NtCurrentTeb();
    expected.Cpsr = 0xa0000000u; /* N and C */
    expected.Fpcr = 0x00400000u; /* round toward +infinity */
    expected.Fpsr = 0x10u;       /* inexact */
    for (i = 0; i < 32; ++i)
    {
        expected.V[i].Low = 0x1122334400000000ull + i;
        expected.V[i].High = 0x5566778800000000ull + i;
    }
    pes13_fex_test_restore(&expected, &observed);
    for (i = 0; i < 31; ++i)
        if (expected.X[i] != observed.X[i]) goto fail;
    if (expected.Sp != observed.Sp || expected.Cpsr != observed.Cpsr ||
        expected.Fpcr != observed.Fpcr || expected.Fpsr != observed.Fpsr ||
        memcmp(expected.V, observed.V, sizeof(expected.V))) goto fail;
    wine_nx_runtime_trace("[FEX2-HOST] PASS full register/NEON/NZCV/FPCR/FPSR exception roundtrip");
    return 1;
fail:
    wine_nx_runtime_trace("[FEX2-HOST] FAIL context roundtrip; refusing to start FEX");
    return 0;
}
