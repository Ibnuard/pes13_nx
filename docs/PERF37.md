# PERF37 JIT probe — diagnostic package

This is a measurement build, **not a claimed performance improvement**. It
retains the PERF36 Box64 execution policy, SAFEFLAGS=2, X87DOUBLE=1 and current
DXVK. Its purpose is to identify the work that prevents moving gameplay from
reaching 30 FPS, using the smoother stationary throw-in as a comparison.

The existing profiler samples the four previously busiest threads for two
seconds per ten-second cycle at 20 ms intervals. A translated-code sample now
also records the actual ARM opcode word, guest block start and guest/native
block sizes. New `[JIT37]`, `[JIT37-WORDS]` and `[JIT37-BLOCK]` lines are bounded.
Only a fixed-size histogram is updated after the sampled thread resumes. No
file output, allocation or added mutex is used while it is paused, and no
counter or helper is injected into executed guest instructions.

One sample word is read from the persistent writable JIT alias, with alignment,
allocation/block bounds and completion checks. The block mapping shares the
existing lock-free profiler assumptions; it is observational, not a consistent
snapshot of all threads. Histograms keep at most 128 opcodes and 128 blocks per
target per report; dropped samples are counted. Only the top 12 block entries
are printed. Existing frame statistics distinguish quiet and sampled phases.

## Hardware test

1. HOME → X → Close. Extract the entire `switch` folder from
   `pes13-perf37-jit-probe.zip` into the SD root and overwrite included files.
   Keep saves, game files and shader caches. It contains one NRO and enables
   `profile=1` in both the unified INI and the game-specific Wine settings.
2. Keep CPU 1728 / GPU 768 / RAM 1600 MHz, 1280×720, teams, stadium and camera.
   Play normal moving gameplay for about one minute after kickoff.
3. During a throw-in, hold the ball above the player's head as long as the game
   allows, then throw and continue. Repeat if practical so a two-second sampling
   burst is likely to observe that phase. Note approximate elapsed time since
   application launch for the held-ball phase and release.
4. Continue moving gameplay for another minute, including a replay/corner if
   convenient. If a lasting slowdown occurs, leave it running another 30 seconds.
   Save `pes13-nx.log` before launching again.

This is not a quiet FPS benchmark: sampling adds overhead and samples include
blocked time. A static high-present phase cannot establish active-match speed.
Use `tools/analyze-perf37.py <log>` to decode opcode categories and counts; it
rejects incomplete histograms rather than inventing missing samples. Native
float instructions can represent x87 or SSE; inspect their guest block before
attributing a bottleneck to one instruction set. Branch samples alone do not
prove a spin loop, and load samples alone do not prove memory bandwidth limits.

After collecting the log, restore `pes13-perf36-scoped-fastnan.zip` to disable
the profiler. No measured 30 FPS result is claimed and startup faults have not
been changed in this package.

## Host validation

The probe fixture runs with address/undefined-behavior sanitizers and verifies
unmapped/misaligned/unfinished/padding rejection, full histograms, retained
counts after saturation, reset and log bounds. Parser fixtures cover multiple
intervals, category decoding, missing/duplicate words and logs without sampling.
Artifact verification compares all 14 generated emitter sources and pass-3
ARM instructions with PERF36, plus unchanged dispatch and scoped-policy data.
The NRO's single executable, icon and metadata are checked. These tests do not
substitute for Switch execution or establish synchronization correctness under
every concurrent block invalidation.
