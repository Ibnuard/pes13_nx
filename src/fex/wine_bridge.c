/* SPDX-License-Identifier: MIT */
#include <switch.h>
#include <stdio.h>
#include <string.h>
#include "ntstatus.h"
#define WIN32_NO_STATUS
#include "windef.h"
#include "winbase.h"
#include "winternl.h"
#undef far /* Wine poisons the obsolete qualifier; libnx uses it as a field. */
#include "wine_bridge.h"
#include "exception_slots.h"

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
C_ASSERT(offsetof(ThreadExceptionDump, cpu_gprs) == 16);
C_ASSERT(offsetof(ThreadExceptionDump, fp) == 248);
C_ASSERT(offsetof(ThreadExceptionDump, fpu_gprs) == 288);
C_ASSERT(offsetof(ThreadExceptionDump, pstate) == 800);
C_ASSERT(offsetof(ThreadExceptionDump, far) == 816);
C_ASSERT(sizeof(ThreadExceptionDump) + PES13_FEX_EXCEPTION_DUMP < PES13_FEX_EXCEPTION_HEADER);

extern void wine_nx_runtime_trace(const char *line);
static int (*handle_exception)(EXCEPTION_POINTERS *);
extern ULONG_PTR wine_nx_call_pe_callback(void *function, const void *arguments, ULONG length, void *teb);

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
    int handled;
    /* Native fault/VM helpers can clobber x18 in prebuilt newlib. Use the
     * runtime's established native-to-PE trampoline to install this thread's
     * Wine TEB for the full FEX call (and restore native x18 on return). */
    pes13_fex_fault_stage(3, context->Pc, record->ExceptionInformation[1], record->ExceptionCode);
    handled = handle_exception && wine_nx_call_pe_callback(handle_exception, &pointers, 0, NtCurrentTeb());
    pes13_fex_fault_stage(4, context->Pc, record->ExceptionInformation[1], handled);
    return handled;
}

struct fault_stage_snapshot
{
    uintptr_t tid;
    unsigned int sequence, stage, status;
    uint64_t pc, address;
};
static struct fault_stage_snapshot fault_stages[32];

void pes13_fex_fault_stage(unsigned int stage, uint64_t pc, uint64_t address, unsigned int status)
{
    TEB *teb = NtCurrentTeb();
    uintptr_t tid = teb ? (uintptr_t)teb->ClientId.UniqueThread : 0;
    unsigned int i;
    if (!tid) return;
    for (i = 0; i < ARRAY_SIZE(fault_stages); ++i)
    {
        struct fault_stage_snapshot *row = &fault_stages[i];
        uintptr_t owner = __atomic_load_n(&row->tid, __ATOMIC_RELAXED);
        if (owner != tid && (owner || !__atomic_compare_exchange_n(&row->tid, &owner, tid, 0,
                                                                   __ATOMIC_RELAXED, __ATOMIC_RELAXED))) continue;
        /* One writer per thread, no allocation/callbacks during publication.
         * All fields atomic so the exit snapshot can read a still-running thread. */
        __atomic_add_fetch(&row->sequence, 1, __ATOMIC_SEQ_CST);
        __atomic_store_n(&row->pc, pc, __ATOMIC_SEQ_CST);
        __atomic_store_n(&row->address, address, __ATOMIC_SEQ_CST);
        __atomic_store_n(&row->status, status, __ATOMIC_SEQ_CST);
        __atomic_store_n(&row->stage, stage, __ATOMIC_SEQ_CST);
        __atomic_add_fetch(&row->sequence, 1, __ATOMIC_SEQ_CST);
        return;
    }
}

void pes13_fex_dump_fault_stages(void)
{
    unsigned int i;
    for (i = 0; i < ARRAY_SIZE(fault_stages); ++i)
    {
        const struct fault_stage_snapshot *row = &fault_stages[i];
        uintptr_t tid = __atomic_load_n(&row->tid, __ATOMIC_RELAXED);
        unsigned int before, after, stage, status;
        uint64_t pc, address;
        char message[208];
        if (!tid) continue;
        before = __atomic_load_n(&row->sequence, __ATOMIC_SEQ_CST);
        stage = __atomic_load_n(&row->stage, __ATOMIC_SEQ_CST);
        pc = __atomic_load_n(&row->pc, __ATOMIC_SEQ_CST);
        address = __atomic_load_n(&row->address, __ATOMIC_SEQ_CST);
        status = __atomic_load_n(&row->status, __ATOMIC_SEQ_CST);
        after = __atomic_load_n(&row->sequence, __ATOMIC_SEQ_CST);
        if (!before || (before & 1) || before != after)
            snprintf(message, sizeof(message), "[FEX3-LAST] tid=%llu snapshot=busy", (unsigned long long)tid);
        else
            snprintf(message, sizeof(message), "[FEX3-LAST] tid=%llu stage=%u pc=%llx address=%llx status=%08x",
                     (unsigned long long)tid, stage, (unsigned long long)pc, (unsigned long long)address, status);
        wine_nx_runtime_trace(message);
    }
}

NTSTATUS pes13_fex_install_dispatcher(HMODULE ntdll, void *module_index, HMODULE cpu, HMODULE wow64)
{
    extern void *pKiUserExceptionDispatcher;
    RTL_RB_TREE **shared;
    void *validate;
    NTSTATUS status;
    struct { void *pc, *base; } probes[3];
    /* Bootstrap bypasses PE LdrInitializeThunk. Its private address index is
     * therefore empty even though the modules are in the native loader's tree.
     * An exception then cannot find FEX/WOW64 .pdata and loops as a leaf unwind.
     * Bind one live tree before guest threads; never duplicate intrusive nodes. */
    if (!ntdll || !module_index || !cpu || !wow64) return STATUS_INVALID_PARAMETER;
    shared = RtlFindExportedRoutineByName(ntdll, "wine_nx_pe_module_index");
    validate = RtlFindExportedRoutineByName(ntdll, "wine_nx_validate_module_index");
    if (!shared || !*shared || !validate) return STATUS_REVISION_MISMATCH;
    if (*shared != module_index && (*shared)->root) return STATUS_INVALID_PARAMETER;
    *shared = module_index;
    pKiUserExceptionDispatcher = RtlFindExportedRoutineByName(ntdll, "KiUserExceptionDispatcher");
    if (!pKiUserExceptionDispatcher) return STATUS_PROCEDURE_NOT_FOUND;
    probes[0].pc = pKiUserExceptionDispatcher;
    probes[0].base = ntdll;
    probes[1].pc = RtlFindExportedRoutineByName(cpu, "BTCpuSimulate");
    probes[1].base = cpu;
    probes[2].pc = RtlFindExportedRoutineByName(wow64, "Wow64PassExceptionToGuest");
    probes[2].base = wow64;
    status = wine_nx_call_pe_callback(validate, probes, ARRAY_SIZE(probes), NtCurrentTeb());
    if (status)
    {
        wine_nx_runtime_trace("[FEX3-UNWIND] FAIL module index or unwind table; refusing guest startup");
        return status;
    }
    wine_nx_runtime_trace("[FEX3-UNWIND] PASS shared module index; ntdll/FEX/WOW64 unwind tables found");
    return STATUS_SUCCESS;
}

unsigned int pes13_fex_begin_guest_dispatch(void)
{
    static unsigned int count;
    unsigned int index = __atomic_load_n(&count, __ATOMIC_RELAXED);
    do
    {
        if (index >= 12) return 0;
    } while (!__atomic_compare_exchange_n(&count, &index, index+1, 1, __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    return index+1;
}

void pes13_fex_trace_guest_dispatch(unsigned int ticket, const char *stage,
                                   const EXCEPTION_RECORD *record, const CONTEXT *context)
{
    char message[240];
    TEB *teb;
    if (!ticket || ticket > 12) return;
    teb = NtCurrentTeb();
    snprintf(message, sizeof(message),
             "[FEX3-SEH] ticket=%u tid=%llu stage=%s code=%08x address=%llx pc=%llx sp=%llx",
             ticket, teb ? (unsigned long long)(uintptr_t)teb->ClientId.UniqueThread : 0,
             stage, record ? (unsigned int)record->ExceptionCode : 0,
             record ? (unsigned long long)(uintptr_t)record->ExceptionAddress : 0,
             context ? (unsigned long long)context->Pc : 0,
             context ? (unsigned long long)context->Sp : 0);
    wine_nx_runtime_trace(message);
}

extern void pes13_fex_test_restore(CONTEXT *requested, CONTEXT *observed);

static int context_check(uint64_t seed)
{
    CONTEXT expected = {0}, observed = {0};
    unsigned int i;
    expected.ContextFlags = CONTEXT_FULL | CONTEXT_ARM64_X18;
    for (i = 0; i < 31; ++i) expected.X[i] = (0x1020304000000000ull + i) ^ seed;
    expected.X[18] = (uintptr_t)NtCurrentTeb();
    expected.Cpsr = 0xa0000000u; /* N and C */
    expected.Fpcr = 0x00400000u; /* round toward +infinity */
    expected.Fpsr = 0x10u;       /* inexact */
    for (i = 0; i < 32; ++i)
    {
        expected.V[i].Low = (0x1122334400000000ull + i) ^ seed;
        expected.V[i].High = (0x5566778800000000ull + i) ^ seed;
    }
    pes13_fex_test_restore(&expected, &observed);
    for (i = 0; i < 31; ++i)
        if (expected.X[i] != observed.X[i]) goto fail;
    if (expected.Sp != observed.Sp || expected.Cpsr != observed.Cpsr ||
        expected.Fpcr != observed.Fpcr || expected.Fpsr != observed.Fpsr ||
        memcmp(expected.V, observed.V, sizeof(expected.V))) goto fail;
    return 1;
fail:
    return 0;
}

int pes13_fex_context_preflight(void)
{
    int passed = context_check(0);
    wine_nx_runtime_trace(passed ?
        "[FEX2-HOST] PASS full register/NEON/NZCV/FPCR/FPSR exception roundtrip" :
        "[FEX2-HOST] FAIL context roundtrip; refusing to start FEX");
    return passed;
}

#ifdef PES13_FEX_ISOLATED_EXCEPTIONS
#define FAULT_WORKERS 4
#define FAULT_ROUNDS 16
extern unsigned char pes13_fex_exception_slots[];
static unsigned int barrier_enabled, barrier_count, barrier_generation, barrier_failed;
static unsigned int workers_start;
static Thread fault_workers[FAULT_WORKERS];
static unsigned int worker_results[FAULT_WORKERS];

/* Called only at our exact original preflight UDF, never at a game fault.
 * Keep four live handlers at once so shared-dump/stack corruption is exposed.
 * No malloc, logging, pthread/Wine locks or floating point in this barrier. */
void pes13_fex_context_fault_barrier(void)
{
    unsigned int generation;
    uint64_t start;
    if (!__atomic_load_n(&barrier_enabled, __ATOMIC_ACQUIRE)) return;
    generation = __atomic_load_n(&barrier_generation, __ATOMIC_ACQUIRE);
    if (__atomic_add_fetch(&barrier_count, 1, __ATOMIC_ACQ_REL) == FAULT_WORKERS)
    {
        __atomic_store_n(&barrier_count, 0, __ATOMIC_RELAXED);
        __atomic_add_fetch(&barrier_generation, 1, __ATOMIC_RELEASE);
        return;
    }
    start = armGetSystemTick();
    while (__atomic_load_n(&barrier_generation, __ATOMIC_ACQUIRE) == generation &&
           !__atomic_load_n(&barrier_failed, __ATOMIC_ACQUIRE))
    {
        if (armGetSystemTick() - start > armNsToTicks(5000000000ull))
        {
            __atomic_store_n(&barrier_failed, 1, __ATOMIC_RELEASE);
            break;
        }
        svcSleepThread(1000000);
    }
}

static void fault_worker(void *argument)
{
    unsigned int id = (uintptr_t)argument, i;
    while (!__atomic_load_n(&workers_start, __ATOMIC_ACQUIRE)) svcSleepThread(1000000);
    for (i = 0; i < FAULT_ROUNDS; ++i)
    {
        if (__atomic_load_n(&barrier_failed, __ATOMIC_ACQUIRE)) return;
        if (!context_check(((uint64_t)(id + 1) << 32) | i))
        {
            __atomic_store_n(&barrier_failed, 1, __ATOMIC_RELEASE);
            return;
        }
        worker_results[id]++;
    }
}

int pes13_fex_fault_stress(void)
{
    unsigned int i, started = 0;
    Handle handles[FAULT_WORKERS];
    wine_nx_runtime_trace("[FEX3-FAULT] testing 4 simultaneous native handlers x 16 rounds");
    __atomic_store_n(&barrier_enabled, 1, __ATOMIC_RELEASE);
    for (i = 0; i < FAULT_WORKERS; ++i)
    {
        if (R_FAILED(threadCreate(&fault_workers[i], fault_worker, (void *)(uintptr_t)i,
                                  NULL, 65536, 59, -2))) goto fail;
        if (R_FAILED(threadStart(&fault_workers[i]))) { threadClose(&fault_workers[i]); goto fail; }
        handles[started++] = fault_workers[i].handle;
    }
    __atomic_store_n(&workers_start, 1, __ATOMIC_RELEASE);
    for (i = 0; i < started; ++i)
    {
        int index;
        if (R_FAILED(svcWaitSynchronization(&index, &handles[i], 1, 20000000000ull))) goto fail;
    }
    __atomic_store_n(&barrier_enabled, 0, __ATOMIC_RELEASE);
    for (i = 0; i < started; ++i) threadClose(&fault_workers[i]);
    for (i = 0; i < FAULT_WORKERS; ++i) if (worker_results[i] != FAULT_ROUNDS) goto fail;
    if (__atomic_load_n(&barrier_failed, __ATOMIC_ACQUIRE)) goto fail;
    for (i = 0; i < PES13_FEX_EXCEPTION_COUNT; ++i)
        if (__atomic_load_n((uintptr_t *)(pes13_fex_exception_slots + i * PES13_FEX_EXCEPTION_STRIDE),
                            __ATOMIC_ACQUIRE)) goto fail;
    wine_nx_runtime_trace("[FEX3-FAULT] PASS 64 roundtrips; 4 overlapping handlers; all slots released");
    return 1;
fail:
    __atomic_store_n(&barrier_failed, 1, __ATOMIC_RELEASE);
    __atomic_store_n(&workers_start, 1, __ATOMIC_RELEASE);
    wine_nx_runtime_trace("[FEX3-FAULT] FAIL concurrent handler test; refusing guest startup");
    return 0;
}
#endif
