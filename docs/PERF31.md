# PERF31: native fence polling and complete submit measurements

This candidate changes the Horizon graphics driver. It is not another Box64
preset change. Switch testing is still required: neither a 30 FPS match nor a
fix for the persistent post-event slowdown is established.

## Why this change

[The fresh PERF30 audit](PERF30-RESULT.md) finds two distinct problems: a game
worker remains near one full CPU core, and a sampled PERF29 run spends much
longer inside graphics submission after its cadence collapses. Audio continues.
The PERF30 log itself ends before it captures that same severe collapse.

The driver currently scans channel error notifications after every unsuccessful
native fence query, including a nonblocking query. Those scans acquire a device
list lock and query native events. Mesa uses these fence queries while collecting
timeline points; repeatedly scanning error notifications can add unnecessary
native work to submission.

PERF31 always performs the native completion query. After a zero-time timeout,
it limits optional error-notification scans for the same thread, device and
syncpoint to one per 50 ms. A different key or a backwards clock forces a scan.
Blocking waits, actual native errors and already latched device loss retain
their behavior. A failed scan invalidates the gate. A newly arriving channel
error may be reported on a later poll; this is an experimental policy, not a
cache of successful fence completion.

The host test executes the actual patched wait function with simulated native
services: 10,000 incomplete queries still make 10,000 completion checks, while
same-time optional error scans fall to one. It also checks completion, errors,
positive/infinite waits, device/syncpoint changes and the exact 50 ms boundary.
This proves the tested semantics, **not** the frequency or cost of these calls
on Switch. If those polls are rare, this optimization may save little.

## Measurement correction

PERF30 instrumented a Horizon object in libvulkan, but the final executable
selected its uninstrumented copy from libEGL. PERF31 replaces all matching
archive copies and verifies measurement calls inside the final linked ELF.

New stage measurements cover full submit entry, creation/destruction, signal
unwrapping, timeline collection/installation, native fence queries/waits and
error scans. Existing queue/channel/audio stages remain. Reports are emitted
every ten seconds; CPU sampling is off. These are nested host wall times, not
GPU execution times, and must not be added as independent frame costs.

The main package preserves the PERF29 control's CPU policy and data files:
SAFEFLAGS=2, X87DOUBLE=1, STRONGMEM=1, scoped FASTROUND=1/CALLRET=2,
worker block growth off, existing matrix/copy changes and audio buffering.

## Install and test

1. Close PES from HOME, then merge the `switch` folder from
   `pes13-perf31-fence-poll.zip` into the SD root, replacing its files.
2. Launch the existing forwarder to
   `sdmc:/switch/pes13-nx/pes13-nx.nro`. There is one NRO, with its icon embedded.
   The package uses the existing game installation and preserves saves/settings.
3. Keep the comparison clocks and scene consistent. Last reported clocks were
   CPU 1728 / GPU 768 / RAM 1600 MHz at 1280x720. Test a match through replay,
   foul and goal transitions, ideally at least the first 30 **in-game minutes**.
   After a drop, leave it running another 30–60 real seconds if possible.
4. Copy `switch/pes13-nx/pes13-nx.log` and its available `previous-*` logs before
   further launches rotate them. Note real time since launch for the drop.

The log must identify `pes13-nx-0.2.0-perf31-fence-poll`, report
`[PERF31] submit_diagnostics=1`, and show `[POLL31] enabled=1`.

`pes13-perf31-control.zip` is a small overlay for the **same PERF31 NRO**. It
disables only the new error-scan policy relative to the main package, keeping
measurements enabled. Use this for a matching-scene comparison if needed.
Reapplying the main package restores the policy. Neither overlay is standalone.

`pes13-perf31-quiet.zip` disables detailed stage timing while keeping the policy
on and CPU sampling off. Use it only after saving a diagnostic run to check
whether measurement overhead affects the result. Reapply the main package
before collecting the next detailed log.

## Earlier stability reference

`pes13-perf31-reference-perf25.zip` repackages the original cached PERF25 NRO
without rebuilding it, with its original flags and the shared runtime files
carried forward by the later package recipes. The older ZIP is no longer in
`dist`; this is a new archive, not a byte-for-byte recovery of that ZIP. The
verified original NRO SHA-256 is
`888c77730685a8cff44edf2f07d3146352dbd29b986413a7b2697b20ce9d2d81`.
[The PERF25 result](PERF25-RESULT.md) records recovery after replay. It is a useful
independent historical comparison, but the user's remembered stable build is
not confirmed to be PERF25. Its archived match cadence was around 15 presents/s,
not 30 FPS. A 30-minute game-clock duration is not a frame-rate measurement.
This reference replaces the runtime with PERF25; reapply the full PERF31 main
package afterward, rather than its small control/quiet overlays.

## Local validation and reproduction

Build in WSL with `python3 tools/run-perf31-build.py`, then package with
`python3 tools/package-perf31.py`. Build status, source hashes, archive checks,
linked disassembly and package manifests are under `local/perf31`.

Validation includes metrics concurrency/saturation tests, address/undefined
behavior sanitizers, real fence-function tests, unchanged CPU emitters and
pinned vendor, all Mesa archive copies, actual linked hooks, restored original
sources and ZIP/NRO metadata. Hardware validation remains pending. The
intermittent startup null-read fault has not been fixed by this driver change.
