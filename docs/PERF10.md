# PERF10 — DXVK x86 comparison

Packages for the existing PERF8 NRO / PERF9 experiment. These packages change
DXVK only (plus its configuration and ensuring sampling is off). They do not
change Box64, Wine ntdll, the NRO, controls, game binaries, settings.dat or saves.
The NRO therefore still identifies itself as PERF8. perf10-package.txt records
the installed variant; it is an installation label, not runtime confirmation.

## Install and test

1. Close PES completely from HOME. Back up your current d3d9.dll and dxvk.conf
   if you have changed them beyond the previous PERF8/PERF9 packages.
2. Start with **pes13-perf10-dxvk311.zip**. Extract its switch folder onto the
   SD root, allowing replacement. Use the same forwarder/NRO as before.
3. Test the same teams, stadium, camera and graphics settings at CPU 1728,
   GPU 768, RAM 1600 MHz. Run a match for at least two minutes. Record the
   first-load slowdown separately from sustained match FPS.
4. Close the game. Save pes13-nx.log with the package name. If available,
   also save the DXVK d3d9 log (its version line confirms the DLL loaded).
5. Compare **pes13-perf10-dxvk271.zip** using exactly the same conditions.
   Install one ZIP at a time; do not merge the packages together.
6. Optional **pes13-perf10-dxvk311-cpu.zip** uses 3.1.1 with one shader
   compiler worker and device-local constant streaming disabled. It can
   reduce competing work but may increase initial shader compilation time;
   constant streaming might already be disabled under Auto on this GPU.
7. **pes13-perf10-rollback.zip** restores the original known DXVK
   v3.1-17-g878473ba and PERF8 dxvk.conf. It does not revert PERF9's ntdll.

Both game-local and C:\dxvk copies are replaced to avoid loading a stale DLL.
No new forwarder is required. Profiling and verbose mode stay disabled;
existing low-rate runtime telemetry is retained. Shader caches are not deleted.
Run a second match on each version to separate warm-cache behavior.

## Validation and limits

Official DXVK release archives 3.1.1 and 2.7.1 were downloaded from doitsujin/dxvk
and checked against GitHub's SHA256 asset digests. Only x32/d3d9.dll is used.
The packager checks PE architecture, required exports, reachable normal/delay
imports and API-set forwarding against the existing Wine payload, and verifies
all ZIP members after writing. Package manifests contain hashes and provenance.
The minimal baseline has unresolved optional delay imports; alternatives must
have no missing required imports and no additional unresolved optional imports.
These checks do not validate Vulkan feature behavior or performance on Switch.

This is a renderer experiment, not a claim that 30 FPS is achieved. Broad
Box64 migration is not included: upstream changes its internal structures and
our generated-source patches require a separate integration/build test.

The thread audit found that Horizon's existing server explicitly refuses
suspension of already-running threads. Restoring the upstream PE wrapper alone
would not add a safe suspend implementation. The inherited fake-success path
is a known correctness concern; this package does not attempt to paper over
it with arbitrary sleeps or asynchronous thread suspension.

Build with `python tools/package-perf10-dxvk.py` after placing the official
release tarballs in local/perf10. Validation reports and package hashes are
written there. Existing distribution archives are not overwritten by PERF10.
