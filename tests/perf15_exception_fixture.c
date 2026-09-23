/* LGPL-2.1-or-later. Host probes for the actual upstream-derived fault helpers. */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "unixlib.h"

typedef union { uint64_t q[1]; uint32_t dword[2]; } test_reg;
typedef struct { test_reg regs[8], ip; union { uint64_t x64; } eflags; int df; } x64emu_t;
enum { _SP = 4, _SI = 6, d_none = 0 };
struct nx_engine { x64emu_t emu; NTSTATUS status; sigjmp_buf escape; int *held_mutex; int dynarec; };
static struct nx_engine *active_engine;
static struct { int mutex_dyndump; } core_context;
void *current_helper;
int fillblock_active;
static sigjmp_buf compiler_escape;
static uintptr_t mapped_pc, guest_pc;
static int pc_is_translated = 1, pc_maps = 1;
int wine_nx_box64_is_translated_pc(uintptr_t pc) { return pc_is_translated && pc == mapped_pc; }
int wine_nx_box64_pc_to_x86(uintptr_t pc, uintptr_t *x86)
{ assert(pc == mapped_pc); *x86 = guest_pc; return pc_maps; }
void cancelFillBlock(void) { siglongjmp(compiler_escape, 1); }

/* ACTUAL_FAULT_HELPERS */

static EXCEPTION_RECORD last_record;
static int raise_code, raises;
NTSTATUS WINAPI Wow64RaiseException(int code, EXCEPTION_RECORD *rec)
{ last_record = *rec; raise_code = code; ++raises; return STATUS_SUCCESS; }
/* ACTUAL_PE_DISPATCH */

static struct nx_engine test_engine;
static unsigned long long registers[31];
static uint32_t native_instruction;
static unsigned char *guest_code;

static void reset_guest(void)
{
    memset(&test_engine, 0, sizeof(test_engine));
    test_engine.dynarec = 1;
    active_engine = &test_engine;
    current_helper = NULL; fillblock_active = 0;
    for (int i = 0; i < 31; ++i) registers[i] = 0x1000 + i;
    memset(guest_code, 0x90, 16);
    guest_pc = (uintptr_t)guest_code;
    mapped_pc = (uintptr_t)&native_instruction;
    pc_is_translated = pc_maps = 1;
}

int main(void)
{
    ULONG address, access;
    I386_CONTEXT ctx = {0};
    struct winebox64_run_params params = {0};
    guest_code = mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS|MAP_32BIT, -1, 0);
    assert(guest_code != MAP_FAILED && (uintptr_t)guest_code <= UINT32_MAX);
    reset_guest();
    active_engine = NULL;
    assert(!wine_nx_box64_handle_fault(4, 0, mapped_pc, registers));
    active_engine = &test_engine;
    assert(!wine_nx_box64_handle_fault(0x100000000ull, 0, mapped_pc, registers));

    /* A translated null read has a stale saved EIP; export native registers/IP. */
    test_engine.emu.ip.q[0] = 0xff6bd55c;
    if (!sigsetjmp(test_engine.escape, 1))
    {
        wine_nx_box64_handle_fault(4, 0, mapped_pc, registers);
        assert(0);
    }
    assert(test_engine.status == STATUS_ACCESS_VIOLATION);
    wine_nx_box64_last_fault(&address, &access);
    assert(address == 4 && access == 0 && test_engine.emu.ip.q[0] == guest_pc);
    for (int i = 0; i < 8; ++i) assert(test_engine.emu.regs[i].q[0] == registers[10+i]);
    assert(test_engine.emu.eflags.x64 == registers[26] && test_engine.emu.df == d_none);
    reset_guest();
    pc_is_translated = 0;
    test_engine.emu.ip.q[0] = 0x1234;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.ip.q[0] == 0x1234);
    pc_is_translated = 1; pc_maps = 0;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.ip.q[0] == 0x1234);
    pc_maps = 1; guest_pc = 0x100000000ull;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.ip.q[0] == 0x1234);

    /* Partial POP/MOVS effects must be undone before the guest sees the fault. */
    reset_guest();
    guest_code[0] = 0x8f; guest_code[1] = 0x00;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SP].dword[0] == registers[14] - 4);
    guest_code[0] = 0x66; guest_code[1] = 0x8f; guest_code[2] = 0x00;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SP].dword[0] == registers[14] - 2);
    guest_code[0] = 0x8f; guest_code[1] = 0xc0;
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SP].dword[0] == registers[14]);
    guest_code[0] = 0xf3; guest_code[1] = 0xa5;
    native_instruction = 0xb8004400; /* STR W0, [X0], #4 */
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SI].dword[0] == registers[16] - 4);
    native_instruction = 0xb81fc400; /* STR W0, [X0], #-4 */
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SI].dword[0] == registers[16] + 4);
    native_instruction = 0xb8404400; /* LDR, not STR */
    recover_translated_state(&test_engine.emu, mapped_pc, registers);
    assert(test_engine.emu.regs[_SI].dword[0] == registers[16]);

    reset_guest();
    test_engine.held_mutex = &core_context.mutex_dyndump;
    current_helper = &test_engine; fillblock_active = 1;
    if (!sigsetjmp(compiler_escape, 1))
    {
        wine_nx_box64_handle_fault(4, 0, mapped_pc, registers);
        assert(0);
    }
    assert(test_engine.status == 0); /* Compiler fallback, no guest exception. */
    fillblock_active = 0;
    if (!sigsetjmp(test_engine.escape, 1))
    {
        wine_nx_box64_handle_fault(0x1234, 1, mapped_pc, registers);
        assert(0);
    }
    wine_nx_box64_last_fault(&address, &access);
    assert(address == 0x1234 && access == 1);

    params.context = &ctx; ctx.Eip = 0x0115c36f;
    params.fault_address = 4; params.fault_access = 0;
    assert(raise_guest_exception(STATUS_ACCESS_VIOLATION, &params));
    assert(raises == 1 && raise_code == -1 && last_record.ExceptionCode == (DWORD)STATUS_ACCESS_VIOLATION);
    assert((uintptr_t)last_record.ExceptionAddress == ctx.Eip);
    assert(last_record.NumberParameters == 2 && last_record.ExceptionInformation[0] == 0 && last_record.ExceptionInformation[1] == 4);
    params.fault_access = 1;
    assert(raise_guest_exception(STATUS_ACCESS_VIOLATION, &params) && last_record.ExceptionInformation[0] == 1);
    params.fault_access = 8;
    assert(raise_guest_exception(STATUS_ACCESS_VIOLATION, &params) && last_record.ExceptionInformation[0] == 8);
    assert(raise_guest_exception(STATUS_BREAKPOINT, &params));
    assert(raise_code == -1 && (uintptr_t)last_record.ExceptionAddress == ctx.Eip && last_record.NumberParameters == 1);
    assert(raise_guest_exception(STATUS_INTEGER_DIVIDE_BY_ZERO, &params) && raise_code == 0);
    assert(raise_guest_exception(STATUS_ILLEGAL_INSTRUCTION, &params) && raise_code == 6);
    assert(!raise_guest_exception(STATUS_NO_MEMORY, &params));
    assert(!raise_guest_exception(STATUS_TIMEOUT, &params));
    munmap(guest_code, 4096);
    puts("PERF15: native-to-x86 fault context, partial instructions, compiler fallback and PE exception records PASS");
}
