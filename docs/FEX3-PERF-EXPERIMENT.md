# FEX3 alias and scheduler experiment

The Box64 build remains the working control for PES 2013. The attached FEX3
run reached Exhibition and stopped around team selection. Its frame counter
count rose from 1,226 at 55 seconds to 1,515 at 65 seconds (about 29 per
second), then from 1,691 at 75 seconds to 1,801 at 85 seconds (11 per second).
After 95 seconds, two 64 KiB heap commits failed with `c0000022`; both FEX
workers parked, and the Vulkan present count stopped at 1,810. Audio underruns had
already risen from 3 at 55 seconds to 398 at 75 seconds. The preceding slowdown
therefore needs separate investigation from the final memory failure.
Horizon backing allocations rose from 9,725 to 21,301 between the last two
memory-pool samples, indicating substantial mapping churn near the freeze.

The available Box64 reference logged 3,009 frames by 60 seconds and ran into
the match. These cumulative counts are not a controlled FPS comparison because
the two runs were not synchronized to the same game scene. They do confirm that
FEX startup/2D behavior still needs improvement.

Both new FEX candidates cache the RW address of each active JIT CodeMemory
arena inside the PE module. This removes the native callback and mapping scan
from repeated instruction writes; the native host is still used for allocation,
release, cache flush, and any unknown range. A linked ARM64 test exercised 129
in-arena writes with only one native alias lookup, then checked ordinary-memory
fallback, release/reuse, and boundary rejection. The NRO also sends at most 24
Horizon mapping-failure details to `fex-runtime.log`, so the next failed
commit can be assigned to backing allocation, reservation, mapping, or another
stage without turning on per-call SD logging.
The cache does not yet remove the guest heap/mapping churn. The next device
log should identify which Horizon step rejects the commit before changing it.

`control` retains the old `Sleep(0)` scheduler behavior. `samecore` changes
only that behavior, from a yield that permits migration to a yield on the same
core. The prior log recorded about 658,000 `NtDelayExecution` calls in the
15–25 second interval, making this a plausible CPU-cost experiment. It is not
yet evidence of faster gameplay: both candidates require Switch measurement.

Build the native control with `tools/build-fex-runtime.py --integration
--native-only`, and the scheduler variant with the additional
`--samecore-yield` option. The FEX DLL is shared between both packages.
Install one ZIP at a time at the microSD root, leaving the existing game,
configuration, prefix, and save data in place. Close through HOME → X before
relaunching. Compare time to menu, team-selection response, audio underruns,
and present deltas over the same scene at the same clocks. Save each
`fex-runtime.log` before launching another run. A rollback ZIP restores the
exact earlier NRO and DLL.

The new DLL, native runtime, ABI, allocator, lookup memory, and code-growth
tests build/pass locally. Neither variant has yet been verified on the Switch,
and no 30 FPS claim is made.
