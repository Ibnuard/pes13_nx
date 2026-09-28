// SPDX-License-Identifier: MIT
// ARM64 PE -> Horizon callbacks. Only zero, one or two integer/pointer
// arguments are supported by host ABI 1. Windows reserves x18 for the TEB;
// Horizon's prebuilt newlib may use it as a caller-saved temporary. Keep the
// incoming value per invocation in a register preserved by both ABIs.
// Callbacks must return normally: C++/SEH unwinding across native code is not
// part of this C ABI. Hardware faults use the separate context bridge.
.text
.p2align 2
.globl PES13FexCallHost
.def PES13FexCallHost; .scl 2; .type 32; .endef
.seh_proc PES13FexCallHost
PES13FexCallHost:
    stp x29, x30, [sp, #-32]!
    .seh_save_fplr_x 32
    str x19, [sp, #16]
    .seh_save_reg x19, 16
    mov x29, sp
    .seh_set_fp
    .seh_endprologue
    mov x19, x18
    mov x16, x0
    mov x0, x1
    mov x1, x2
    blr x16
    mov x18, x19
    .seh_startepilogue
    ldr x19, [sp, #16]
    .seh_save_reg x19, 16
    ldp x29, x30, [sp], #32
    .seh_save_fplr_x 32
    .seh_endepilogue
    ret
    .seh_endproc
