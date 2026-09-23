# PERF8 CPU sampling findings

Input: cpu-sampling-on.log, SHA256 afd00f06c0c0221b1239fe3a2b0c0f339428e5d5dc11dd08e668ef0b9fe950ca.
Sampler started successfully at 2 ms, four busiest registered threads.
PERF8 block policy active. No code or build changes made in this analysis.

For reports labelled uptime 200-320 s (samples summarize the preceding interval),
thread 72 has 64,006 samples: 93.0% translated x86, 1.0% ARM64 PE,
5.9% native, 0.0% SVC after rounding. Module summaries average about 61.7%
PES executable and 28.0% x86 ntdll. Thread 124: 91.1% translated x86,
0.1% PE, 0.5% native, 8.1% SVC; about 89.0% executable in module summaries.
Module summaries are rounded separately and may drop addresses from finite buckets.
These are sampled locations, NOT CPU-time percentages: blocked threads can be sampled.
Use THREADS alongside them; thread 72 repeatedly consumes nearly a full core.

Using runtime-perf8-block-profile/wine-nx-runtime.elf, native offsets resolve to:
- 0x16682c0: memset
- 0x165e6c0: memcpy
- 0x373dc0: getDB
- 0x37525c: wine_nx_box64_run
- 0xd7c34: NtWaitForAlertByThreadId
- 0xffdbc: wine_nx_do_syscall
- 0xbcff0: horizon_futex_wait
- 0xd5ee4: NtDelayExecution

The local release's x86 ntdll exports place RVA 0x531c0 in
RtlEnterCriticalSection, 0x53300 in RtlLeaveCriticalSection and 0x52cbf in
RtlpWaitForCriticalSection. The exact SD DLL was not independently hashed.
Main-thread late samples often include futex/critical-section waits; these
cannot be counted as CPU execution. The leading native sites are not NVK.

Conclusion: current evidence prioritizes translated game code and synchronization.
It does not establish the pure translation overhead fraction, prove a spin loop,
or rule out secondary Vulkan-driver overhead. The four-thread sampler does not
cover every driver worker and does not measure GPU duration. Short host present
calls are not full GPU/frame times. FPS with sampling enabled is not a baseline.

Next: examine repeated game/lock call sites and lock ownership before applying
any wait/locking optimization. Keep compatibility semantics; do not simply
remove locks or weaken ordering based on utilization. Re-disable sampling for
performance comparisons using the supplied OFF configuration.
