# HIGH compiler scratch reserve candidate

This candidate targets the confirmed FEX compiler allocation failure in the
2026-10-04 transition trace. It is a native host-adapter change, not a change to
the frozen FEX DLL, graphics preset, game timing or replay frame rate. Console
validation remains required.

## Evidence

The input `transition.log` has SHA-256
`3d0a8941969b1d508a2c418d8a40efb854270e904730b08fb9b0706f72020d03`.
The private archive is `local/high-freeze-review/3d0a8941969b/`.

At approximately 211,690 ms on the trace clock (sample 213,166 minus event age
1,476), the same native thread reports:

```
EVENT kind=3 code=00000005 thread=54818c detail=8388608 address=1000
[FEX2-HEAP] STOP compiler scratch failed bytes=0x0000000000800000
[EXC] ... pc=0xff68bb88 ...
[EXC] unhandled status=0x80000003; parking thread
```

Allocator event 5 is `aligned_alloc`: 8 MiB requested, 4-KiB alignment. The
observed DLL base is `ff540000`, so the breakpoint is RVA `14bb88`, matching the
frozen DLL's fatal `Stop` helper. Thus this trace identifies a compiler workspace
allocation failure followed by a parked thread. It is not just evidence of a
low frame rate. Presentation continues at about 59 calls/second afterward,
consistent with moving spectators while the match stops; this does not measure
the game's simulation rate.

The nearby memory sample reports 137,043,312 bytes free within the allocator and
1,593,344 bytes of untaken native heap, together about 132.21 MiB. Only 16,384
bytes are in the allocator's top chunk. The aggregate free total cannot prove
there is an aligned contiguous 8-MiB block; fragmentation is a strong candidate,
but the trace does not contain a full free-block map.

`transition.previous.log` is a different startup failure: native code mapping
reports `rc=0xd401` / `errno=22`, followed by guest exit code 3. The scratch fix
does not specifically repair that mapping failure.

## Change and limits

At FEX host bootstrap, reserve four separate page-aligned 8-MiB native buffers
before the guest and renderer workers fragment the heap. The existing host ABI
v3 scratch callbacks lend these buffers for exactly 8-MiB rounded requests.
An explicit release returns a buffer to this pool instead of the general heap.
Each live allocation has exclusive ownership; no busy buffer is reclaimed.

If all slots are busy, preserve normal aligned allocation and honest failure.
Other allocation sizes and general FEX heap/code mappings retain their existing
paths. Failure to reserve all four slots at startup leaves a smaller pool and
does not itself abort initialization. Libc allocation/free never executes while
holding the pool mutex.

The reserve has a 32-MiB ceiling. Idle reserved buffers reduce memory available
to other allocations; this is not additional RAM. More than four concurrent
8-MiB requests can still need normal allocation and can still fail. These are
explicit constraints to evaluate in the next device trace, not a guarantee that
every HIGH failure is solved.

The package keeps the input fix, compact keyboard and grouped settings preview.
The frozen `libwow64fex.dll` remains SHA-256
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.
The production runtime lock is unchanged. Only a copy of the frozen native
adapter is patched; unrelated live experimental FEX changes are excluded.
Local native dependency differences from the approved production archive are
retained in `evidence/dependency-diff.json`.

## Diagnostics and validation

The opt-in v3 observer still samples every two seconds for at most 20 minutes.
An additional `SCRATCH` line records ready slots, current busy slots, reserve
hits, fallback attempts/failures, peak busy slots, returns and bootstrap failures.
No per-frame filesystem logging is added to the scratch path.

The build receipt identifies the NRO, ELF and every patched native source.
Host ASan/UBSan checks inject allocation pressure with zero, two and four slots,
exercise concurrent use and cross-thread general heap frees, and verify that
buffers stay distinct and remain usable when new 8-MiB allocations fail. ARM64
checks execute the linked host table and scratch callbacks with modeled libc
and Horizon mutex services. Existing input, keyboard, silent logging, trace and
Vulkan wrapper checks also run against the delivered build. These checks do not
substitute for real Horizon memory behavior or PES gameplay testing.

## Device test

1. Close PES via HOME, X, Close. Copy the package's `switch` folder to the SD
   root, replacing its two files. Keep the existing game, saves and runtime DLLs.
2. Use HIGH and Default DXVK with the same fixed clocks as the preceding run.
3. Play beyond the previous failure point, preferably 10 minutes, including
   repeated replay, ball-out, corner and goal transitions.
4. If the match freezes while spectators still move, let the trace run another
   10 seconds when possible, close the app, then preserve `transition.log`.
   For a second run, preserve `transition.previous.log` too.
5. Send the logs even if the run succeeds: pool occupancy and failed allocations
   determine whether the reserve is adequate or merely delays the failure.

Remove `switch/pes13-fex/launcher/diagnostics.txt` to turn tracing off. To undo
the reserve change, copy `rollback/switch` to the SD root; this restores the
previous v3 diagnostic NRO. A disabled observer alone does not disable the pool.

This package is a targeted fix candidate. It does not claim verified HIGH
stability, faster gameplay, or elimination of the independent startup fault.
