# PERF34 DXVK A/B packages

These archives keep the verified PERF34 NRO, Box64 preset, `configuration.ini`,
PES path and controller profile unchanged. They replace only the x86 D3D9 DLL,
in both locations that the Wine-NX loader can search: the game directory and
`drive_c/dxvk/d3d9.dll`. This avoids accidentally benchmarking a stale DLL
left by an older SD installation.

The reference package is the generated `pes13-perf34-dxvk-current.zip`, which
keeps the retained Wine-NX DXVK build (reported by the runtime as DXVK 3.1.1)
and writes the same DLL to both locations. The original
[`dist/pes13-perf34-config.zip`](../dist/pes13-perf34-config.zip) is otherwise
the same PERF34 profile, but its archive predates this explicit duplicate-path
guard. The two experimental overlays are:

| Package | Renderer | Purpose |
| --- | --- | --- |
| `pes13-perf34-dxvk-1103.zip` | Official DXVK 1.10.3 x86 D3D9 | Latest official 1.10 branch candidate |
| `pes13-perf34-dxvk-sarek-1111.zip` | DXVK-Sarek 1.11.1 x86 D3D9 | Legacy/backport build with Mali compatibility changes |

The upstream DXVK project documents 1.10.3 as a legacy release with relaxed
driver requirements. DXVK-Sarek is a community fork of the 1.10.x line that
backports fixes and game configurations; its 1.11.1 release is advertised as a
Mali GPU fix. The Switch path here uses Tegra NVK, not Mali, so Sarek is an
experiment rather than a guaranteed Switch optimization. Sources and SHA-256
hashes are stored in each archive's `DXVK-VARIANT.json`.

## Hardware test order

1. Run `pes13-perf34-dxvk-current.zip` as the reference.
2. Close the app with **HOME → X → Close**.
3. Install one DXVK overlay, keeping the same 1728/768/1600 MHz clocks,
   1280×720 settings, game match and controller path.
4. The first run can compile a new shader/state cache. Compare the second and
   third runs with the same scene. Keep `pes13-nx.log` after each run.
5. Restore the reference package before trying the other overlay.

Copy the archive's `switch` directory over the existing `switch` directory;
do not mix DLLs from two variants. The archives contain no game executable,
installation registry or saved game.

Use sustained moving gameplay for the comparison. Menu animation and a
throw-in while the ball is stationary can exceed 30 FPS even when normal play
does not. A limiter cannot create frames that the translated game thread does
not produce. If both legacy DLLs remain near the current 17–20 presents/s and
the log still shows low `host_present` time with a busy translated worker, the
next bottleneck is Box64/game CPU translation rather than the Vulkan present
path.

The baseline and overlays are deliberately separate so a regression in an old
DXVK build can be rolled back by copying the reference package. No claim of a
30 FPS result is made until a matched Switch run confirms it.
