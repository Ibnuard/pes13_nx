/* SPDX-License-Identifier: MIT
 * Synthetic AArch64 memory kernels, copied into the real FEX RW/RX adapter.
 * These are addressing prototypes, NOT output from a modified FEX compiler.
 * x0 = host bias; w1 = 32-bit guest start; w2 = iterations; w3 = node mask.
 * Direct and biased kernels consume identical 32-bit guest pointers/data.
 * Only caller-saved registers are used; x18 (Wine TEB) is never touched.
 */
.text
.macro begin name
    .balign 64
    .global \name
    .type \name, %function
\name:
.endm
.macro finish name
    .global \name\()_end
\name\()_end:
    .size \name, .-\name
.endm

.macro chase name, biased
begin \name
    mov w1, w1
    cbz w2, 2f
1:
    .rept 8
    .if \biased
        ldr w1, [x0, w1, uxtw]
    .else
        ldr w1, [x1]
    .endif
    .endr
    subs w2, w2, #1
    b.ne 1b
2:  mov w0, w1
    ret
finish \name
.endm
chase as39_chase_direct, 0
chase as39_chase_bias, 1

/* Each node is 32 bytes. A relatively-prime stride visits every node. */
.macro next_node payload
    add w8, w8, #97
    and w8, w8, w3
    add w10, w1, w8, lsl #5
    add w10, w10, #\payload
.endm

.macro scalar name, biased
begin \name
    mov w4, wzr
    mov w8, wzr
    cbz w2, 2f
1:  next_node 4
    .if \biased
        ldr w11, [x0, w10, uxtw]
    .else
        ldr w11, [x10]
    .endif
    add w11, w11, #1
    .if \biased
        str w11, [x0, w10, uxtw]
    .else
        str w11, [x10]
    .endif
    eor w4, w4, w11
    subs w2, w2, #1
    b.ne 1b
2:  mov w0, w4
    ret
finish \name
.endm
scalar as39_scalar_direct, 0
scalar as39_scalar_bias, 1

.macro vector name, biased
begin \name
    mov w8, wzr
    movi v1.4s, #1
    movi v2.4s, #0
    cbz w2, 2f
1:  next_node 16
    .if \biased
        ldr q0, [x0, w10, uxtw]
    .else
        ldr q0, [x10]
    .endif
    add v0.4s, v0.4s, v1.4s
    .if \biased
        str q0, [x0, w10, uxtw]
    .else
        str q0, [x10]
    .endif
    eor v2.16b, v2.16b, v0.16b
    subs w2, w2, #1
    b.ne 1b
2:  addv s2, v2.4s
    fmov w0, s2
    ret
finish \name
.endm
vector as39_vector_direct, 0
vector as39_vector_bias, 1

/* LDP/STP and exclusive accesses cannot fuse a second base register. */
.macro pair name, biased
begin \name
    mov x4, xzr
    mov w8, wzr
    cbz w2, 2f
1:  next_node 16
    .if \biased
        add x10, x0, w10, uxtw
    .endif
    ldp x11, x12, [x10]
    add x11, x11, #1
    add x12, x12, #3
    stp x11, x12, [x10]
    eor x4, x4, x11
    eor x4, x4, x12
    subs w2, w2, #1
    b.ne 1b
2:  mov x0, x4
    ret
finish \name
.endm
pair as39_pair_direct, 0
pair as39_pair_bias, 1

.macro atomic name, biased
begin \name
    mov w4, wzr
    mov w8, wzr
    cbz w2, 3f
1:  next_node 4
    .if \biased
        add x10, x0, w10, uxtw
    .endif
2:  ldaxr w11, [x10]
    add w11, w11, #1
    stlxr w12, w11, [x10]
    cbnz w12, 2b
    eor w4, w4, w11
    subs w2, w2, #1
    b.ne 1b
3:  mov w0, w4
    ret
finish \name
.endm
atomic as39_atomic_direct, 0
atomic as39_atomic_bias, 1

/* Compute x86-32 effective address BEFORE adding the 64-bit host bias. */
begin as39_wrap_read
    add w1, w1, w2
    ldr w0, [x0, w1, uxtw]
    ret
finish as39_wrap_read
.section .note.GNU-stack,"",%progbits
