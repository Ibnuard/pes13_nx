/* SPDX-License-Identifier: MIT */
#ifndef PES13_FEX_WINE_BRIDGE_H
#define PES13_FEX_WINE_BRIDGE_H
#include "horizon_host.h"
#define PES13_WOW64_BACKEND_FEX 0x46455832u
/* Wine types must be included before this header. */
NTSTATUS pes13_fex_install_module(HMODULE module);
NTSTATUS pes13_fex_install_dispatcher(HMODULE ntdll, void *module_index, HMODULE cpu, HMODULE wow64);
int pes13_fex_dispatch_exception(EXCEPTION_RECORD *record, CONTEXT *context);
void pes13_fex_restore_context(const CONTEXT *context) __attribute__((noreturn));
int pes13_fex_context_preflight(void);
int pes13_fex_fault_stress(void);
void pes13_fex_context_fault_barrier(void);
void pes13_fex_trace_guest_dispatch(unsigned int ticket, const char *stage,
                                   const EXCEPTION_RECORD *record, const CONTEXT *context);
unsigned int pes13_fex_begin_guest_dispatch(void);
/* Per-thread last-fault snapshots: no I/O until process exit. */
void pes13_fex_fault_stage(unsigned int stage, uint64_t pc, uint64_t address, unsigned int status);
void pes13_fex_dump_fault_stages(void);
#endif
