/* SPDX-License-Identifier: MIT
 * Hardware preflight: restore every register, take an ordinary UDF through
 * the Wine fault bridge, and capture the result before touching scratch regs.
 */
.text
.balign 4
.global pes13_fex_test_restore
.type pes13_fex_test_restore, %function
pes13_fex_test_restore:
    sub sp, sp, #256
    stp x19, x20, [sp, #0]
    stp x21, x22, [sp, #16]
    stp x23, x24, [sp, #32]
    stp x25, x26, [sp, #48]
    stp x27, x28, [sp, #64]
    stp x29, x30, [sp, #80]
    stp q8, q9, [sp, #96]
    stp q10, q11, [sp, #128]
    stp q12, q13, [sp, #160]
    stp q14, q15, [sp, #192]
    mrs x2, fpcr
    mrs x3, fpsr
    stp x2, x3, [sp, #224]
    str x1, [x0, #8]  /* expected.X0 = observed */
    mov x2, sp
    str x2, [x0, #256]
    adr x2, pes13_fex_test_fault
    str x2, [x0, #264]
    b pes13_fex_restore_context
.global pes13_fex_test_fault
pes13_fex_test_fault:
    .inst 0x00000000
    /* x0 is the output CONTEXT; store everything before using scratch. */
    stp x0, x1, [x0, #8]
    stp x2, x3, [x0, #24]
    stp x4, x5, [x0, #40]
    stp x6, x7, [x0, #56]
    stp x8, x9, [x0, #72]
    stp x10, x11, [x0, #88]
    stp x12, x13, [x0, #104]
    stp x14, x15, [x0, #120]
    stp x16, x17, [x0, #136]
    stp x18, x19, [x0, #152]
    stp x20, x21, [x0, #168]
    stp x22, x23, [x0, #184]
    stp x24, x25, [x0, #200]
    stp x26, x27, [x0, #216]
    stp x28, x29, [x0, #232]
    str x30, [x0, #248]
    stp q0, q1, [x0, #272]
    stp q2, q3, [x0, #304]
    stp q4, q5, [x0, #336]
    stp q6, q7, [x0, #368]
    stp q8, q9, [x0, #400]
    stp q10, q11, [x0, #432]
    stp q12, q13, [x0, #464]
    stp q14, q15, [x0, #496]
    stp q16, q17, [x0, #528]
    stp q18, q19, [x0, #560]
    stp q20, q21, [x0, #592]
    stp q22, q23, [x0, #624]
    stp q24, q25, [x0, #656]
    stp q26, q27, [x0, #688]
    stp q28, q29, [x0, #720]
    stp q30, q31, [x0, #752]
    mov x1, sp
    str x1, [x0, #256]
    mrs x1, nzcv
    str w1, [x0, #4]
    mrs x1, fpcr
    str w1, [x0, #784]
    mrs x1, fpsr
    str w1, [x0, #788]
    ldp x2, x3, [sp, #224]
    msr fpcr, x2
    msr fpsr, x3
    ldp x19, x20, [sp, #0]
    ldp x21, x22, [sp, #16]
    ldp x23, x24, [sp, #32]
    ldp x25, x26, [sp, #48]
    ldp x27, x28, [sp, #64]
    ldp x29, x30, [sp, #80]
    ldp q8, q9, [sp, #96]
    ldp q10, q11, [sp, #128]
    ldp q12, q13, [sp, #160]
    ldp q14, q15, [sp, #192]
    add sp, sp, #256
    ret
.size pes13_fex_test_restore, .-pes13_fex_test_restore
.section .note.GNU-stack,"",%progbits
