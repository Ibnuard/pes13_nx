# PERF1 performance experiment

Close PES from HOME and back up the installed pes13-nx.nro and
drive_c/PES13/pes2013.box64.txt. Copy the overlay's switch directory to the SD.
Use the same existing game forwarder. Do not copy a settings.dat: retain the
working preset, saves and controller setup from your successful match.

PERF1 changes BIGBLOCK from 0 to 1 and supplies DXVK_SHADER_CACHE_PATH as
C:\dxvk-cache, creating that directory before Wine starts. It retains SAFEFLAGS,
STRONGMEM, X87DOUBLE, FASTNAN, FASTROUND and CALLRET compatibility values.
The experiment does not promise an FPS improvement; larger blocks can regress
compatibility. Restore the two backed-up files if loading regresses.

Play the same stadium, teams, camera and resolution for at least three minutes.
Repeat once so the second run can reuse any successfully written shader cache.
Return switch/pes13-nx/pes13-nx.log after closing the application.
Look for the build marker pes13-nx-0.2.0-perf1 and BIGBLOCK=1.

[PERF1] measures Vulkan presents separately from the mixed compositor/frame
counter. It is a long-interval present rate, not a GPU timing measurement.
[PERF1-SUSPEND] records the first eight suspension statuses and then one in
524288 calls. It preserves the original suspend behavior and return status.
Do not enable verbose or sampling profiler flags for this comparison.

The initial match log contains millions of duplicate/query/close/suspend
requests. The ARM64 RtlWow64SuspendThread implementation performs exactly
that sequence. Horizon refuses suspension of running threads. Sparse status
records are needed before attributing the traffic to a retry loop.

Build via WSL: PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf-test.py
Do not run another build against the same tree simultaneously. Production
source and linked outputs are restored even if compilation fails. Restored
sources are touched so subsequent production builds replace diagnostic objects.
