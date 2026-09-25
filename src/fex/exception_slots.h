/* SPDX-License-Identifier: MIT */
#ifndef PES13_FEX_EXCEPTION_SLOTS_H
#define PES13_FEX_EXCEPTION_SLOTS_H
/* One live exception owns its frame AND stack until the final context restore.
 * Nested faults take another slot. The entry never allocates or calls C. */
#define PES13_FEX_EXCEPTION_COUNT 64
#define PES13_FEX_EXCEPTION_HEADER 4096
#define PES13_FEX_EXCEPTION_STACK 65536
#define PES13_FEX_EXCEPTION_STRIDE 69632
#define PES13_FEX_EXCEPTION_DUMP 16
#endif
