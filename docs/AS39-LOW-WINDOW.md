# PES13: assessment of Autorun's low guest window

This is a source audit, not a new Switch runtime or boot package. No kernel,
loader, NSP, game or production runtime was installed or changed by this audit.

The task **Port Sleeping Dogs ke Switch**
(`01a11234-82e3-7da0-a8a2-d4d098806fac`) audited Autorun commit
`cbb0e4e6e7fa7f47f328d92441f51bfb507f266f`. Its report is in the sibling project:
`sleepingdogs-fex/reports/autorun-low-window-audit.json`. At inspection it marked
`hardware_tested`, `runtime_changed` and `new_switch_build_produced` false.
Its passing host checks use modeled kernel calls.

## What changes the earlier PES result

Our actual device probes already measured a 2048 MiB budget in 32-bit no-alias
mode and 3285 MiB in 39-bit mode. The ordinary 39-bit kernel rejected mapping
PES at `0x00400000` with `0xd401`; mapping at `0x10000000` and high native JIT
execution passed. The EXE has no relocation directory and needs its low base.
See [the recorded probe](AS39-EXPERIMENT.md).

Autorun supplies a kernel **and loader** patch that places native code above
`0x100000000` and opens a guest mapping window from `0x00200000` to
`0x100000000`. Its runtime reserves that window early and verifies executable
mapping at `0x00400000` and writable aliasing near `0xffff0000`. This directly
addresses the first blocker observed in the PES probe.

These mappings alias backing pages; they do not duplicate their physical RAM.
The approach can preserve guest addresses directly rather than adding software
address bias to every guest load/store. This is a design benefit, not a measured
PES performance result.

## Memory limits

- **4 GiB describes the low virtual address domain**, not an available physical
  heap. Non-LAA Windows programs also retain their normal 2 GiB guest limit;
  low mapping availability does not automatically make an EXE LAA.
- The measured process-budget improvement is **1237 MiB**, about 60.4%, before
  runtime/driver/stack overhead. A full 4 GiB heap is not supported by the data.
- Moving native FEX/Wine/driver allocations out of the low guest region could
  reduce contention and leave more backing RAM for Kitserver. Allocation failure
  handling, fragmentation and lifetime bugs still need independent fixes.

## PES port requirements

1. Adapt the kernel/loader title whitelist: upstream enables only Autorun title
   `0548eabb35576000`. Match the kernel base and boot path; a 39-bit NSP alone
   cannot create the low window.
2. Add a separate experimental 39-bit forwarder and preflight. Reserve the low
   window before libnx/native mappings and verify low RX plus high-edge RW alias
   operations on the console before attempting to launch PES.
3. Adapt the current 32-bit-only launch check and guest VA policy only for a
   **verified** low-window layout. Merely bypassing the existing check is unsafe.
4. Route high native backing into low Wine guest views with correct protection,
   ownership and release. Audit FEX/WoW64 callback pointers and Vulkan mappings
   returned to x86: a native pointer above 4 GiB cannot be truncated to 32 bits.
5. Run guest fault/SMC/JIT tests and the patched Kitserver workload on the device.
   The existing AS39 probe proves high JIT execution, not complete Wine/FEX/PES
   operation in this new layout.

The immediate Kit17 candidate remains on the existing 32-bit no-alias runtime.
It addresses DXVK allocation granularity and NULL storage from the current log;
it is not an AS39 port.

## Pinned primary references

- [Kernel/loader patch and boot requirements](https://github.com/autorunhq/autorun/blob/cbb0e4e6e7fa7f47f328d92441f51bfb507f266f/horizon-wine/mesosphere/README.txt)
- [Title-gated low-window patch](https://github.com/autorunhq/autorun/blob/cbb0e4e6e7fa7f47f328d92441f51bfb507f266f/horizon-wine/mesosphere/low-window.patch)
- [Runtime reservation and low-address probes](https://github.com/autorunhq/autorun/blob/cbb0e4e6e7fa7f47f328d92441f51bfb507f266f/horizon-wine/source/low_window.c)
