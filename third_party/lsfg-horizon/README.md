# Native LSFG for FEXTendo

Optional native ARM64 frame interpolation for the Vulkan presentation path.
The setting defaults to OFF. It does not change PES13's simulation clock or
reduce FEX translation work. Optical flow adds GPU work and can make a GPU-bound
scene slower; successful host builds do not establish Switch performance.

## Provenance

- LSFG-VK backend: GPL-3.0-or-later archive commit
  `8b0da2661c6f3473a7fccc8ba643880050e71642`, from
  https://git.lsfg-vk.dev/lsfg-vk-archive.git.
  This is the last GPL archive revision used by this port, not the later release
  under a noncommercial/no-derivatives license.
- `horizon.patch`, the four NVK shaders, `nvk_shaders.hpp`, CMake recipe and
  cross-toolchain file: Autorun switch-dev commit
  `0fff003d388139829b303382b13c14c5344672b2`, https://github.com/autorunhq/switch-dev.
  The borrowed-device API and NVK reductions derive from NaGaa95/Cemu-nx
  `fcae0752`. Two large reduction passes use separate 8x8 dispatches; their output
  is not assumed bit-identical to upstream.
- `src/runtime/fextendo_lsfg.cpp` and its headers adapt Autorun presentation glue
  at `a52bb803819e856821cef9c19917675736df1529`, GPL-3.0-or-later,
  https://github.com/autorunhq/autorun.
- FEXTendo adds local-prefix builds, resource validation before enablement,
  project SD paths, separate original/generated counters, and integration into
  this Wine fork's existing instrumentation and presentation serialization.
  Unsupported presentation extension chains conservatively use ordinary
  presentation without consuming the game's wait semaphore.

The upstream GPL text is included as `LICENSE.md`. Public combined-runtime
packages must include corresponding source and these changes/build scripts.

## Build

```
python3 tools/build-fextendo-lsfg.py
```

Requires devkitA64/libnx, CMake, Ninja, glslangValidator, and the same Vulkan
headers used by the native runtime. The script installs under
`local/fex3/lsfg-build/install`; it never changes global SDK libraries. All native
objects reserve ARM64 register x18 for Wine's TEB. Pass the prefix to the runtime
builder with `--lsfg-prefix local/fex3/lsfg-build/install`.

## User payload

Copy your own compatible Steam `Lossless.dll` to:

```
sdmc:/switch/pes13-fex/lsfg/Lossless.dll
```

The DLL is parsed as data, never loaded as Windows code. This pinned backend
requires its FP32 SPIR-V resource set. The supplied test DLL, Lossless Scaling
**3.2.1.0**, SHA-256
`8b7dbc11b2ea544650af2ed4ffc92da3abd88ec5afa09c36484c060fbc848834`,
contains 202 DXBC resources and no SPIR-V resources, so this build rejects it
before touching the game swapchain. Obtain a compatible DLL from your own Steam
installation; no proprietary DLL or extracted shader data is distributed here.
Compatibility is based on required resources, not merely a version string or
x64 architecture. Restart the launcher after replacing the DLL.

Supported path: SDR RGBA8/BGRA8, one swapchain and graphics+compute presentation
queue. The bridge keeps two source frames and inserts one interpolated frame,
using FIFO and the Switch's single-acquired-image present/reacquire sequence.
The first two frames warm temporal history. First use may compile LSFG pipelines;
the separate cache is `sdmc:/switch/pes13-fex/cache/lsfg-vk.bin`.

`[LSFG] frames original=... generated=... bypassed=...` counts successful native
presents. The existing game FPS and frame-gap counters remain tied to real game
presents. Frame generation is not evidence that first-kickoff freezes are fixed.
