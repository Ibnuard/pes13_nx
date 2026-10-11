/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PES_LOW_WINDOW_H
#define PES_LOW_WINDOW_H
#include <stdint.h>
#define FXT_GUEST_BASE UINT64_C(0x200000)
#define FXT_NATIVE_BASE UINT64_C(0x100000000)
#define FXT_HOST_END UINT64_C(0x8000000000)
static inline int fxt_low_window_layout(uint64_t base, uint64_t size) {
    return base == FXT_GUEST_BASE && size == FXT_HOST_END - FXT_GUEST_BASE;
}
int fxt_low_window_preflight(void);
void fxt_low_window_report(void);
const char *fxt_low_window_error(void);
#endif
