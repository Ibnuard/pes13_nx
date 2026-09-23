# PERF35 fast-jumptable

PERF35 is a source-level CPU experiment built from the known-good PERF34
configuration and current DXVK package. It keeps the same PES13 path,
`configuration.ini`, Box64 compatibility preset, controller profile and DXVK
DLLs. Only `pes13-nx.nro` changes.

**Correction, 2026-09-23:** These two cleanups were already applied by the
inherited PERF8 build recipe in PERF34. PERF35 did not introduce them. The
generated dispatch source, dynablock source and dispatch object were identical
in the compared PERF34 and PERF35 builds. The earlier claim of a new CPU
optimization was incorrect. Keep the released archive as a historical artifact;
do not interpret its build number as evidence of a performance improvement.

Both builds already:

- remove the optional `SAVE_MEM` fifth jump-table level, which adds memory
  work to translated-block jumps;
- remove the `wine_nx_box64_block_tests` and
  `wine_nx_box64_native_entries` diagnostic atomic increments from generated
  dispatch/validation code.

The exported diagnostic symbols remain for ABI compatibility. Mutex handling,
`SAFEFLAGS=2`, `X87DOUBLE=1`, `FASTROUND=0`, PERF33 scoped fastmath, and all
previous startup guards are unchanged. The build uses the established `-O1`
Box64 emitter setting. There is no new jump-table memory tradeoff versus PERF34.

## Test

Copy the archive's `switch` directory over the current PES13-NX directory.
Keep the same 1728/768/1600 MHz clocks, 1280×720 resolution, game settings and
match. Close each run with **HOME → X → Close**. Let the first run warm the
existing DXVK cache, then compare the second and third runs against
`pes13-perf34-dxvk-current.zip` in the same moving gameplay scene after
kick-off. Keep the logs from both runs.

This is an A/B candidate, not a 30 FPS guarantee. A frame limiter cannot
create frames that the translated game thread does not produce; the supplied
DXVK logs showed roughly 1 ms host-present time versus roughly 55–60 ms frame
time. This measures that call only; it does not exclude driver work elsewhere
or GPU work. See PERF35-RESULT.md for the subsequent log audit and PERF36.md
for the actual new emitter change.
