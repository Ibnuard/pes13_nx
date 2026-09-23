/* SPDX-License-Identifier: MIT */
#ifndef PES13_FEX_WINE_BRIDGE_H
#define PES13_FEX_WINE_BRIDGE_H
#include "horizon_host.h"
#define PES13_WOW64_BACKEND_FEX 0x46455832u
/* Wine types must be included before this header. */
NTSTATUS pes13_fex_install_module(HMODULE module);
int pes13_fex_dispatch_exception(EXCEPTION_RECORD *record, CONTEXT *context);
void pes13_fex_restore_context(const CONTEXT *context) __attribute__((noreturn));
int pes13_fex_context_preflight(void);
#endif
