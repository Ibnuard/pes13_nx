# PERF16 — 3D CPU samples and renderer comparison on stable PERF15

These are reversible overlays for the **existing PERF15 installation**.
They contain no replacement NRO, winebox64.dll, ntdll.dll, game EXE, save,
controller profile or settings.dat. They do not claim a measured speedup.
The build marker remains `pes13-nx-0.2.0-perf15-guest-exceptions`.

Hardware results are recorded in [PERF16-RESULT.md](PERF16-RESULT.md):
WineD3D also runs slowly, while DXVK samples concentrate in translated
game code. The configurations below describe the original test procedure.

## Recommended first: sample the slow match

1. Close via HOME → X → Close. Extract **pes13-perf16-sample-3d.zip** at
   the SD root and overwrite. Use the same forwarder, graphics settings and
   clock settings as the stable run. This overlay expects DXVK 3.1.1 to be
   installed, as confirmed by the supplied log.
2. Reach the team-selection screen showing the players; stay there about
   **30 real seconds**. Then enter a match and let it run for **60 real
   seconds after kickoff**, not 60 seconds on the in-game clock. Note the
   approximate transition times if practical.
3. Close fully and save `switch/pes13-nx/pes13-nx.log` before another run
   overwrites it. Expected: `[PROF] sampler started` and subsequent `[PROF]`
   records for the busy threads. If sampling is not granted by the forwarder,
   send that log; do not recreate the forwarder speculatively.
4. Extract **pes13-perf16-restore-dxvk.zip** to turn sampling off and restore
   the same official DXVK 3.1.1 app-local DLL for normal play.

The sampler briefly pauses the four busiest threads every 2 ms and writes
summaries at reporting intervals. It changes timing and adds overhead;
sampled FPS must not be treated as a production benchmark. Samples include
blocked time as well as running time. They will be interpreted together with
kernel CPU occupancy and symbolized using the exact PERF15 ELF. The target
thread selection follows the previous ten-second report, so remaining in
the match for several intervals matters.

## Optional second: WineD3D/OpenGL comparison

After collecting the DXVK samples, close the app and extract
**pes13-perf16-wined3d.zip** at the SD root. Sampling and verbose logging
are off. It selects Wine's D3D9 implementation and installs the original,
digest-verified Wine d3d9.dll next to pes2013.exe, where it takes precedence
over any previous app-local DXVK DLL. The installed WineD3D/OpenGL modules
are the same base runtime dependencies. CSMT is explicitly set to 1.

Changing `d3d9=wine` alone would be insufficient if DXVK's d3d9.dll remained
next to the EXE. This package handles both parts. It does not remove or
change the DXVK DLL under `C:\dxvk` or its cache.

Use the same team, stadium, camera, graphics preset and clocks. Compare the
same screen and match duration with sampling off; save the log even if
WineD3D fails to initialize. Expected startup messages mention `Direct3D 9
Wine` and `csmt=1`; a game-renderer `DXVK: v3.1.1` banner should not appear.
`[PERF8]` measures **Vulkan** presents, so zero there is normal on OpenGL;
use the `gl_frames` progress counters, visual behavior and any independent
frame measurement instead. Do not read the Vulkan-only counter as zero
OpenGL FPS. Runtime OpenGL surface messages alone are not sufficient proof
of a WineD3D game renderer, because the compositor also uses OpenGL.

Restore **pes13-perf16-restore-dxvk.zip** afterward. It restores the official
3.1.1 D3D9 DLL and `d3d9=dxvk`, with profiling off and BIGBLOCK=0. The CSMT
text file is ignored in DXVK mode. It restores the renderer control state
of this comparison, not arbitrary settings introduced outside these tests.

## Interpretation

- If WineD3D is much faster in the same scene, prioritize DXVK/Vulkan bridge,
  NVK CPU work and GPU synchronization. It would not identify the exact bug.
- If both are similarly slow and samples concentrate in game/Box64 code,
  focus on translated game execution and synchronization.
- If samples concentrate in Mesa/native code or GPU waits, investigate that
  path; CPU busy percentages and fast present calls alone cannot exclude it.

The host packager verifies the PE32 DLL identity/imports, config values,
ZIP contents and hashes, and that the overlays exclude the stable NRO/ABI4
pair. Required imports resolve. The minimal dependency set still has
125 deferred-import findings for DXVK and 131 for WineD3D, so the full
static import check is not clean. WineD3D additionally reaches delayed
GLU tessellation helpers from opengl32.dll; they were not called in a
hardware test here. WineD3D performance and compatibility remain unverified.
