# PERF14 — preserve address reservations during mapping changes

This NRO-only test builds on PERF11 / Box64 0.4.4 and keeps the installed
PERF13 ARM64 ntdll. It targets a demonstrated mapping race window, not a
measured 3D rendering optimization. Hardware confirmation is pending.

Three mapping paths previously released an address reservation before its
replacement was installed. libnx native allocations share the address space
but do not take Wine's mapping mutex. They could claim these temporary holes.
The anonymous MAP_FIXED path already used a transition reservation; this
change applies the same ownership principle to the remaining paths:

- Section split/decommit keeps the parent's reservation until all replacement
  pieces exist, and keeps it during rollback if allocation of a piece fails.
- Anonymous commit holds a temporary reservation across metadata splitting
  and backing allocation.
- Fixed section replacement holds a temporary reservation from before unmap
  until the replacement owns its own reservation, releasing the guard on
  success and failure.

This does not remove collision checks or force a mapping over native memory.
Kernel failures can still leave an allocation unsuccessful; the patch does
not make every MAP_FIXED operation transactional or recover existing address
fragmentation. It also does not prove these windows caused the user's
bad_alloc; that needs a new hardware run.

## Install

With PERF13 already installed, close PES via HOME -> X -> Close. Extract
**pes13-perf14-map-guards.zip** into the SD root and overwrite `switch`.
The NRO path is still `switch/pes13-nx/pes13-nx.nro`; no new forwarder is
needed. The log should now identify `pes13-nx-0.2.0-perf14-map-guards`.

Try three launches in sequence without rebooting, closing fully between
each. Save each log before the next launch overwrites it. On a successful
run, try the same team-selection screen and about one in-game minute of a
match at the same clocks/settings. A repeat startup failure remains useful
evidence even if the visible screen is still the loading spinner.

**pes13-perf14-rollback-nro.zip** restores the byte-identical PERF11 NRO used
with PERF13 (SHA256
`98ce549f65046fa44457dc36508cc1e5c65019cb94156e706e6d109ed64190f4`).
It keeps the installed PERF13 suspend-backoff DLL. This rollback returns
the previous runtime, not PERF12's suspend behavior.

Both packages reassert the same profile-off / fixed-Compatible configuration.
They do not include replacement DLLs, DXVK, Box64 preset files, controller
settings, game data or saves. No shader-cache deletion is requested.

## Verification

`tests/perf14_mappings.py` extracts the actual three transition functions.
A host fixture probes every reservation removal/allocation as a competing
native allocator could. The old functions expose addresses in all three
paths. The patched functions preserve coverage; failure-injection checks
exercise section rollback, reservation exhaustion, split failure, backing
failure and failed unmap. This models interleaving rather than the Switch
kernel and does not establish game correctness or performance.

The runtime recipe also checks Compatible policy selection, Box64's -O1 /
no-SAVE_MEM compilation and the earlier conditional ResumeThread wakeup.
NRO icon/NACP/header validation and ZIP CRC/hash checks run on packaging.
The builder restores all temporarily changed baseline sources.

## Upstream comparison

Reviewed upstream's [whole low-address reservation change](https://github.com/danfromtico/autorun/commit/baa030c4e9),
[reservation on larger address spaces](https://github.com/danfromtico/autorun/commit/8a464e7047),
and [section anchor packing](https://github.com/danfromtico/autorun/commit/d7ad2860a1).
Those changes address placement/fragmentation, but do not establish the cause
of this PES crash. The inspected horizon.c at commit
99de116c87e25f35ce345579ed18e86af494c2f8 still releases a section's parent
reservation before creating its replacement pieces. PERF14 is a targeted
local handoff fix; it does not import upstream's whole memory subsystem or
change the native address-space window in the same experiment.
