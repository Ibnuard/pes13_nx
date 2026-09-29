# Upstream audit — 2026-09-20

Read-only comparison. No runtime, dependency pin, or release package changed.

## Verified revisions

- Local Wine-NX basis: `1bc4e45163f0d2328cdfd35c7f471dd9821bb879` (dependencies.json).
- Repository redirects to https://github.com/danfromtico/autorun.
- Inspected main: `99de116c87e25f35ce345579ed18e86af494c2f8`: 108 commits ahead, 273 changed files reported by GitHub compare.
- Latest release: test-build-3, published 2026-09-19 15:11:02 UTC; tag resolves to `f86a318ecaaf4f4730487c4ea312cd0e7e4c4b75`. Main and release are different snapshots.
- Local Box64 pin: `dae0917c47b4edd8956f314210417a20fd225c4b`; upstream bootstrap now pins `2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a` (v0.4.4). API reports 1015 commits ahead. The saved unpaginated response contains only 250 commit entries, so this is not an exhaustive commit audit.
- Local Mesa Switch pin: `b297e230ef88c6c88df2561becf864f979f494a6`; inspected HEAD is one commit ahead, `c689872669` (channel teardown at session exit).

API snapshots and selected raw upstream files are saved under local/upstream-audit/.

## Relevant changes and limits

1. Box64: upstream integration now targets fastDBGetBlock and newer dynarec structures. This is a candidate for a separately built compatibility-preserving test, not a drop-in vendor replacement: generated-source patches in Box64Core.cmake must be adapted and validated. Preserve the known-working PES compatibility settings and local fixes when comparing.
2. Box64 commit `be4db111990826ea860ca5e9e72a3b064bdb4e3e` replaces repeated jump-address searches with a hash lookup in translation. This helps block construction; it does not by itself explain or fix the sustained ~4 FPS intervals where our translation-attempt counter is nearly flat. Commit `3bf34a77c79438ceaf7c76c86da9a4de7507df1b` targets repeated block invalidation and deserves a separate review.
3. Autorun implements user APC dispatch on alertable waits, fixes 32-bit wait return status, and adds waitable timer signaling and exception handling. These are compatibility/scheduling candidates; no PES speedup has been established.
4. Current upstream ARM64 RtlWow64SuspendThread performs handle validation and delegates local suspension to pWow64SuspendLocalThread. Our inherited PERF3 implementation instead reports success without suspension. This local divergence needs investigation independently of the upstream update. Upstream function presence alone does not prove all Horizon suspend semantics are correct.
5. The only newer Mesa patch changes nouveau_horizon_runtime_shutdown: it leaves GPU channels for session teardown. It is not a match-rendering optimization.
6. AMD64, VKD3D, and launcher UI work account for part of the upstream expansion. Those features are not evidence of improved base FPS for 32-bit D3D9 PES13.

## Interpretation and next controlled experiment

PERF9 user-confirmed no-spin still reports approximately 3.7–4.1 successful presents/s in late intervals. Previous sampling was dominated by translated x86 code, while current CPU core occupancy is high. These support investigating guest execution and synchronization first. CPU occupancy also includes spinning and driver work; GPU utilization alone cannot identify the responsible layer or exclude driver CPU overhead. No GPU timestamp breakdown is available.

The reported L4T result is encouraging hardware evidence, but comparison requires matching game scene, resolution, graphics settings, clocks, Box64 settings/version and DXVK version. It does not guarantee 30 FPS under Horizon.

Recommended order: trace suspend/resume target pairing with bounded counters; correct any proven semantic defect; then test newer Box64 in an isolated build with fixed compatibility settings, same scene/clocks and sampling off. Keep PERF8/PERF9 control available. Avoid combining a Box64 upgrade, driver change, aggressive presets, and thread changes in one measurement. No hardware test or new NRO was produced by this audit.

## Sources

- https://github.com/danfromtico/autorun/compare/1bc4e45163f0d2328cdfd35c7f471dd9821bb879...99de116c87e25f35ce345579ed18e86af494c2f8
- https://github.com/danfromtico/autorun/releases/tag/test-build-3
- https://github.com/danfromtico/autorun/blob/99de116c87e25f35ce345579ed18e86af494c2f8/wine-nx-probe/tools/bootstrap-box64-core.sh
- https://github.com/ptitSeb/box64/commit/be4db111990826ea860ca5e9e72a3b064bdb4e3e
- https://github.com/danfromtico/mesa-switch/commit/c689872669
