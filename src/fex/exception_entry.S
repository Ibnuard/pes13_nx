/* SPDX-License-Identifier: MIT
 * FEX2: full ARM64 CONTEXT restoration via Horizon's exception frame.
 * The normal libnx entry is linked under pes13_libnx_exception_entry.
 * A private UDF at one exact PC re-enters the kernel exception protocol. It
 * copies the requested context into its frame and returns with SVC 0x28.
 * Unlike a BR through x9/x17, this does not sacrifice a live JIT register.
 * Layouts are checked against Wine/libnx headers in wine_bridge.c.
 */
.text
.balign 4
.global __libnx_exception_entry
.type __libnx_exception_entry, %function
__libnx_exception_entry:
    cbz x1, pes13_libnx_exception_entry
    ldr x2, [x1, #88]
    adrp x3, pes13_fex_restore_context
    add x3, x3, :lo12:pes13_fex_restore_context
    cmp x2, x3
    b.ne pes13_libnx_exception_entry
    /* Kernel frame's saved x0 is the CONTEXT pointer. x0-x8 are restored
     * from that frame by the kernel, so they are safe scratch registers. */
    ldr x2, [x1]
    ldp x3, x4, [x2, #8]
    stp x3, x4, [x1]
    ldp x3, x4, [x2, #24]
    stp x3, x4, [x1, #16]
    ldp x3, x4, [x2, #40]
    stp x3, x4, [x1, #32]
    ldp x3, x4, [x2, #56]
    stp x3, x4, [x1, #48]
    ldr x3, [x2, #72]
    str x3, [x1, #64]
    ldp x3, x4, [x2, #248]
    stp x3, x4, [x1, #72]
    ldr x3, [x2, #264]
    str x3, [x1, #88]
    ldr w3, [x2, #4]
    str w3, [x1, #96]
    ldr w3, [x2, #784]
    msr fpcr, x3
    ldr w3, [x2, #788]
    msr fpsr, x3
    ldp q0, q1, [x2, #272]
    ldp q2, q3, [x2, #304]
    ldp q4, q5, [x2, #336]
    ldp q6, q7, [x2, #368]
    ldp q8, q9, [x2, #400]
    ldp q10, q11, [x2, #432]
    ldp q12, q13, [x2, #464]
    ldp q14, q15, [x2, #496]
    ldp q16, q17, [x2, #528]
    ldp q18, q19, [x2, #560]
    ldp q20, q21, [x2, #592]
    ldp q22, q23, [x2, #624]
    ldp q24, q25, [x2, #656]
    ldp q26, q27, [x2, #688]
    ldp q28, q29, [x2, #720]
    ldp q30, q31, [x2, #752]
    ldp x9, x10, [x2, #80]
    ldp x11, x12, [x2, #96]
    ldp x13, x14, [x2, #112]
    ldp x15, x16, [x2, #128]
    ldp x17, x18, [x2, #144]
    ldp x19, x20, [x2, #160]
    ldp x21, x22, [x2, #176]
    ldp x23, x24, [x2, #192]
    ldp x25, x26, [x2, #208]
    ldp x27, x28, [x2, #224]
    ldr x29, [x2, #240]
    mov w0, wzr
    svc #0x28
    b .
.size __libnx_exception_entry, .-__libnx_exception_entry

.global pes13_fex_restore_context
.type pes13_fex_restore_context, %function
pes13_fex_restore_context:
    .inst 0x00000000 /* UDF, recognized only at this exact instruction address */
    b .
.size pes13_fex_restore_context, .-pes13_fex_restore_context

/* libnx's dump has no FPCR/FPSR fields. Save them in its padding before C
 * can execute a floating-point operation. This wrapper is not used by the
 * private restore trap above. */
.global __libnx_exception_handler
.type __libnx_exception_handler, %function
__libnx_exception_handler:
    mrs x1, fpcr
    mrs x2, fpsr
    stp w1, w2, [x0, #4]
    b pes13_fex_wine_exception_handler
.size __libnx_exception_handler, .-__libnx_exception_handler
.section .note.GNU-stack,"",%progbits
