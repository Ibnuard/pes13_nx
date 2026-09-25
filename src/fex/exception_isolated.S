/* SPDX-License-Identifier: MIT
 * Horizon AArch64 exception entry. x0-x8 are scratch (saved in kernel frame);
 * x9-x29 and all vectors must remain untouched until copied to our dump.
 * Unlike the default libnx path, no global dump or shared handler stack is
 * used. Each in-flight fault claims a slot with acquire/release atomics.
 */
#include "exception_slots.h"
.bss
.balign 4096
.global pes13_fex_exception_slots
.type pes13_fex_exception_slots, %object
pes13_fex_exception_slots:
    .zero PES13_FEX_EXCEPTION_COUNT * PES13_FEX_EXCEPTION_STRIDE
.size pes13_fex_exception_slots, .-pes13_fex_exception_slots

.text
.balign 4
.global pes13_fex_exception_enter
.type pes13_fex_exception_enter, %function
pes13_fex_exception_enter:
    cbz x1, pes13_fex_exception_abort
    adrp x2, pes13_fex_exception_slots
    add x2, x2, :lo12:pes13_fex_exception_slots
    mov x6, #(PES13_FEX_EXCEPTION_STRIDE >> 12)
    lsl x6, x6, #12
    mov w7, #PES13_FEX_EXCEPTION_COUNT
    mrs x8, tpidrro_el0
    /* A zero TLS value must not make an owned slot look free. */
    cbnz x8, 1f
    mov x8, #1
1:  ldaxr x3, [x2]
    cbnz x3, 2f
    stlxr w4, x8, [x2]
    cbz w4, 3f
2:  clrex
    add x2, x2, x6
    subs w7, w7, #1
    b.ne 1b
    b pes13_fex_exception_abort
3:  add x6, x2, x6          /* private stack top */
    add x2, x2, #PES13_FEX_EXCEPTION_DUMP
    mov x5, x2              /* dump base */
    str w0, [x2], #4
    mrs x3, fpcr
    mrs x4, fpsr
    stp w3, w4, [x2], #8
    str wzr, [x2], #4
    ldp x3, x4, [x1]
    stp x3, x4, [x2], #16
    ldp x3, x4, [x1, #16]
    stp x3, x4, [x2], #16
    ldp x3, x4, [x1, #32]
    stp x3, x4, [x2], #16
    ldp x3, x4, [x1, #48]
    stp x3, x4, [x2], #16
    ldr x3, [x1, #64]
    str x3, [x2], #8
    stp x9, x10, [x2], #16
    stp x11, x12, [x2], #16
    stp x13, x14, [x2], #16
    stp x15, x16, [x2], #16
    stp x17, x18, [x2], #16
    stp x19, x20, [x2], #16
    stp x21, x22, [x2], #16
    stp x23, x24, [x2], #16
    stp x25, x26, [x2], #16
    stp x27, x28, [x2], #16
    str x29, [x2], #8
    ldp x3, x4, [x1, #72]    /* LR, SP */
    stp x3, x4, [x2], #16
    ldr x3, [x1, #88]        /* PC, padding */
    stp x3, xzr, [x2], #16
    stp q0, q1, [x2], #32
    stp q2, q3, [x2], #32
    stp q4, q5, [x2], #32
    stp q6, q7, [x2], #32
    stp q8, q9, [x2], #32
    stp q10, q11, [x2], #32
    stp q12, q13, [x2], #32
    stp q14, q15, [x2], #32
    stp q16, q17, [x2], #32
    stp q18, q19, [x2], #32
    stp q20, q21, [x2], #32
    stp q22, q23, [x2], #32
    stp q24, q25, [x2], #32
    stp q26, q27, [x2], #32
    stp q28, q29, [x2], #32
    stp q30, q31, [x2], #32
    ldp x3, x4, [x1, #96]    /* PSTATE, AFSR0, AFSR1, ESR */
    stp x3, x4, [x2], #16
    ldr x3, [x1, #112]
    str x3, [x2]
    /* Return from the kernel exception protocol before entering C/Wine. */
    str x5, [x1]
    str x6, [x1, #80]
    adrp x3, pes13_fex_exception_handler_entry
    add x3, x3, :lo12:pes13_fex_exception_handler_entry
    str x3, [x1, #88]
    mov w0, wzr
    svc #0x28
    b .
.size pes13_fex_exception_enter, .-pes13_fex_exception_enter

.global pes13_fex_exception_abort
pes13_fex_exception_abort:
    mov w0, #0xf801
    svc #0x28
    b .

.global pes13_fex_exception_handler_entry
pes13_fex_exception_handler_entry:
    bl __libnx_exception_handler
    /* The Wine handler must resume a context or park on an unhandled fault. */
    b pes13_fex_exception_abort
.section .note.GNU-stack,"",%progbits
