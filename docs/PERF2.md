# PERF2 suspend-loop experiment

PERF1 confirmed that PES issued about 2.8 million failed WoW64 thread-suspend
attempts in 62 seconds. Only 10 Vulkan presents completed in that interval and
multiple threads timed out on critical sections. PERF2 restores
BOX64_DYNAREC_BIGBLOCK=0 and keeps the persistent DXVK shader cache.

PERF2 converts Horizon's STATUS_NOT_SUPPORTED suspend result into STATUS_SUCCESS
with previous count 0. Horizon has no safe asynchronous stop primitive for an
already-running pthread, and this runtime hosts the Wine server and Windows
threads inside one process. The fallback prevents PES from retrying the
unsupported request continuously. All other suspend results keep their original
behavior.

Close PES from HOME, then extract the overlay's switch directory to the SD root
and overwrite the listed files. Keep the existing game, settings.dat, saves and
controller profile. Use the same forwarder.

Confirm that the log contains `pes13-nx-0.2.0-perf2-suspend`,
`BOX64_DYNAREC_BIGBLOCK=0`, and `[PERF2-SUSPEND]`. First check whether the intro
and menus advance. If they do, play the same match for at least three minutes,
close the application from HOME, and return `switch/pes13-nx/pes13-nx.log`.

This is an experimental compatibility fallback. If it causes a crash, hang, or
corrupted game state, restore the production NRO and Box64 profile from the
rollback package.

Build via WSL:
`PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf2-test.py`.
The script restores production source and linked outputs even after a failed
build, then touches restored sources so later production builds recompile them.
