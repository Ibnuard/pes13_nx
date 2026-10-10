# Kit11: preserve guest address space before Kitserver asset loading

The Kit10 log SHA-256 is
`04b4825b3107b3ebf8d6ea1c23d649a55af33819f07009b081a473fab60e8719`.
The user confirms the Exhibition/controller-page freeze at about 80 seconds,
with HOME and audio still working. This is a Medium 720p run, DXVK 3.1.1,
32-bit no-alias, with gameplay.dll still in the plugin list.

## Evidence and limits

At 75.787 s, Wine fails a **0xeb0000-byte reservation (14.6875 MiB)** with
`STATUS_NO_MEMORY / c0000017`. The caller is the game's file callback thread
(84). The first allocation of that size had succeeded at 75.639 s; another
one fails. Later smaller allocations succeed. The file read/write thread (76)
then consumes about 3.18 CPU seconds per five-second sample, with its Wine
server thread consuming another 1.44. Server traffic rises to about 86,000
round trips per second. This persists until the log ends at 113.269 s.

Presentation continues at about 32–35 submissions per second. These are
presentation counters, not proof that the frozen scene advances or that
gameplay achieves that FPS. No lasting Vulkan call is identified by this log.
The confirmed allocation failure precedes the freeze, but its causal link to
the later returning busy loop still requires a device comparison.

The kernel lists 796 MiB as unmapped, including a 102-MiB hole inside the
excluded native heap interval and uncommitted Wine reservations. Neither is
automatically available for a new guest reservation. The exhaustive Wine
search and the previous libnx recovery already exist; repeating those fixes
does not create a larger contiguous address range.

`gameplay.dll` also fails attachment at 13.862 s with `c0000005`, after which
the game continues to its menu. It remains a separate confirmed compatibility
issue; this build does not claim to repair that plugin.

## Candidate change

On the logged stack region `0x00200000–0x40000000`, the early Wine reservation
ceiling moves from `0x20100000` to `0x30000000`. This protects **255 MiB more
virtual address space** before native mappings can fragment it. It does not
preallocate that much physical RAM; pages still commit on demand.

At least **256 MiB of the native stack region remains outside this early
reservation**. This is an address window, not a guarantee of free physical
RAM. Small regions retain the old half-region limit. Larger-than-32-bit modes
and unknown/invalid regions do not use the policy. Existing Wine free-range
exclusions, reservation ownership checks and kernel mapping checks remain.
The FEX DLL, JIT cache sizes, renderer and performance presets are unchanged.

For an explicit same-NRO control, set `guest_va_headroom=0` in the existing
`[compatibility]` section of configuration.ini. The default is 1. Do not
replace the user's whole configuration. Debug startup reports `VA-PARTITION`
with the actual ceiling and native window. A Kit10 NRO rollback is packaged.

Debug launch also reports the busiest existing NT/server counters (`WAIT-HOT`)
and recent completed-call statuses (`WAIT-RECENT`). These require no new
producer hooks, guest pointer reads, thread suspension or synchronous SD writes.
Recent slot counts are samples, not estimated call rates. Ordinary launch
remains quiet.

## Validation and device test

Host sanitizer tests cover policy bounds and the concurrent recorder. Linked
ARM64 checks exercise the startup range clipping and legacy control, plus the
existing guarded reservation replacement/search and the debug/quiet boundaries.
The fragmentation fixture is modeled; it is not a reconstructed console map.

First test with the same plugins, Medium preset, renderer and clocks as Kit10.
Use Debug launch, enter Exhibition/controller settings, and proceed to team
selection and kick-off if possible. If the same freeze returns while HOME
responds, allow about 15 seconds of observations before closing normally.
Keep the new runtime log even if the game succeeds. The device success criteria
are absence of the 0xeb0000 reservation failure and progress beyond the stalled
menu, not merely a higher presentation count.

This is a fix candidate for address-space pressure. Console behavior, the
Exhibition freeze and long-match stability are not yet verified on Kit11.
