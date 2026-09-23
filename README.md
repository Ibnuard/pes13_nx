# PES13-NX

PES 2013 PC on Nintendo Switch, using a custom PES13-NX Horizon runtime built
from Wine-NX/Wine, Box64's ARM64 dynamic recompiler, and Direct3D 9 through
DXVK + Mesa NVK. Upstream credits and licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md).

The `experimental/fex-core` branch starts a [FEX port for Horizon](docs/FEX2-BRINGUP.md).
The FEX1 JIT adapter probe passed on Switch. FEX2 now connects the ARM64 WOW64
module to Wine, adds an exception bridge and supplies an original x86 test in
a separate package. The compact-heap build has now
[passed its complete x86 guest test on Switch](docs/FEX2-RESULT.md), including
SSE, x87, executable-code invalidation and one worker's TLS isolation and exit.
The native register/exception, heap, physical-counter and callback ABI
preflights also pass. Concurrent fault handling and PES integration are the
next gates; this smoke test does not measure game FPS. The game runtime still
uses Box64.

Hardware testing has reached matches at 1280x720 with XInput gamepad control.
The experimental PERF27 runtime improves notification routing, while earlier
changes specialize translation of measured PES CPU hotspots. Recent match
segments measure about 15–19 successful presents/s; smooth 30 or 60 FPS match
play is not established. Replay/transitions still stutter and intermittent
startup crashes remain. [PERF28 sampling](docs/PERF28-RESULT.md) identifies a
saturated translated game worker; [PERF29](docs/PERF29.md) tests scoped block
growth with a same-NRO control. The stall also reproduced with growth disabled;
[the fresh PERF30 audit](docs/PERF30-RESULT.md) finds a busy game worker and
incomplete driver timing coverage. The [PERF31-labelled uploads](docs/PERF31-RESULT.md)
actually ran PERF25 because a settings-only overlay retained the older NRO.
[PERF32](docs/PERF32.md) tests larger translated game blocks on the PERF25 base;
every variant includes its NRO. Its [first result](docs/PERF32-RESULT.md) still
shows long sections around 12 presents/s; the log ends at the reported corner,
before the subsequent slowdown is captured. A 30 FPS match and a startup fix
remain unproven. Menus running near 60 FPS
do not establish match performance or full-match compatibility.

The earlier [PERF33 fastmath](docs/PERF33.md) experiment keeps the
same renderer and startup path but scopes `FASTNAN=1`, `STRONGMEM=0` and
`FORWARD=1024` to newly translated game blocks after the first present. This
is an intentionally aggressive CPU experiment; use its same-NRO control or
the PERF32 package if ordering or stability regresses. No 30 FPS result is
claimed until a matched Switch run confirms it.

The configuration migration is [PERF34 CONFIG](docs/PERF34.md). It keeps
the PERF33 runtime and replaces the collection of root-level `0`/`1` files
with one `switch/pes13-nx/configuration.ini`. Existing sidecar files remain a
read-only fallback inside the runtime, so older SD layouts still boot. The
PERF34 ZIPs do not ship those boolean sidecars; use the `config` variant for
the tested profile, `control` to disable PERF33 blocks, or `diagnostics` to
enable the profiler. This is a configuration migration, not a new FPS claim.

The latest hardware candidate is [PERF38 region fusion](docs/PERF38.md), based
on the [PERF37 instruction samples](docs/PERF37-RESULT.md). It reduces redundant
x87 rounding setup in eligible regions of measured math blocks while retaining
the existing DXVK and Box64 preset. Host tests pass; Switch performance is
unverified. The quiet package includes one NRO and supports a same-NRO control
through `perf38_region_fusion=0`. No stable 30 FPS gameplay result is claimed.
Its [first Switch run](docs/PERF38-RESULT.md) confirms the optimization was
applied, while the event-linked busy game worker still limits match cadence.

This project contains source changes, build tools and configuration. Supply
your own installed PES 2013 files and installation metadata. Game executables,
assets, installation codes, logs and release binaries are excluded from Git.
The small generated `settings.dat` is included because it reproduces the
user-tested PC preset that enables XInput.

## Install

1. Copy the runtime package's `switch` folder to the SD card.
2. Copy your game to `switch/pes13-nx/drive_c/PES13/`. It must contain
   `pes2013.exe`, its accompanying game DLLs and the `img` directory.
3. Export metadata from your existing Windows installation with
   `python tools/export-metadata.py`, then copy the locally generated
   `local/config/pes13-install.reg` to `switch/pes13-nx/pes13-install.reg`.
   This copies existing values; it does not generate an installation code.
4. Create/update a Sphaira forwarder targeting **`sdmc:/switch/pes13-nx/pes13-nx.nro`**,
   using **32-bit address space, no alias, 4 cores**, as in the successful run.
   No executable arguments are needed; the NRO opens PES automatically.

```text
switch/
  pes13-nx/
    pes13-nx.nro                    # the complete native runtime; launches PES
    pes13-install.reg               # your private installation metadata
    drive_c/
      PES13/                        # your game + supplied settings
      users/steamuser/Documents/
        KONAMI/Pro Evolution Soccer 2013/settings.dat  # active PES preset
      dxvk/d3d9.dll
      windows/                      # required Wine modules and fonts
    share/wine/                     # required fonts and NLS data
```

When upgrading, copy the new package's `switch` folder, including its NRO,
controller files and `drive_c/users/steamuser/Documents` profile. PES reads its
active `settings.dat` from Documents, not from the installation directory.
Remove old duplicate
NROs at `switch/pes13-nx.nro` and `switch/pes13-nx/pes13-nx-runtime.nro` if
present, then point the forwarder to the path above. The data folder remains
required. Old `target.txt` and `run-entry.txt` files are no longer read.

The icon must be embedded in the NRO, not merely copied alongside it. Sphaira's
installer rejects an empty icon with `SphairaError_OwoBadArgs`. Package 0.1.2
introduced a 256x256 baseline JPEG icon and the application metadata (NACP),
which remain included in 0.2.0.

Keep `pes2013.wine-nx.txt` and `pes2013.box64.txt` supplied by this project.
The first selects DXVK, framebuffer windows and quiet logging; the second
retains the compatibility preset that worked on hardware. The `.wine-nx.txt`
suffix is part of the upstream configuration format. PERF34's
`configuration.ini` controls the small boolean runtime switches; these two
structured files remain separate because they contain settings rather than a
single boolean value per file.

The runtime writes `switch/pes13-nx/pes13-nx.log`. If troubleshooting is needed,
share that log from the new build. Do not upload `pes13-install.reg` or saved
registry files. Close the application from HOME before replacing its files.

## Controller

Buttons follow Xbox positions: **Switch B = Xbox A (confirm)**, A = Xbox B,
Y = Xbox X and X = Xbox Y. The production profile enables PES's built-in
XInput path and suppresses controller-to-keyboard and controller-to-mouse
fallbacks. Plus is Start and ZL/ZR are Xbox triggers.

Hold **L + R while opening the NRO** to enter **Controller Check**. Press
ABXY, move both sticks, then press and release Plus to continue to PES.
The check only reads controller state; it cannot change graphics or open
`settings.exe`. It shows the native buttons and their XInput translation;
it does not by itself prove the game consumed the input.

For a failed in-game test, share `switch/pes13-nx/pes13-nx.log`. Production
input tracing is off. See [controller diagnostics](docs/CONTROLLER.md) for the
mapping, production settings and the optional diagnostic switches.

## Build and repository layout

Build natively in WSL; see [the build guide](docs/BUILD.md). There is no Docker
requirement. Source revisions and toolchain versions are recorded in
[dependencies.json](dependencies.json).

| Directory | Purpose |
| --- | --- |
| `src/` | PES startup, registry helpers and XInput forwarder |
| `patches/` | Changes against the pinned Wine-NX source |
| `config/` | PES configuration and dependency manifests |
| `assets/` | Project icon and its generation notes |
| `tools/`, `tests/` | WSL builds, packaging and host checks |
| `local/` | Ignored private game, metadata, baseline and diagnostics |
| `dist/` | Ignored assembled SD payload and runtime ZIP |

The public ZIP is built from an explicit file list. It excludes game files and
private registry data even when those are present in the local SD payload.
OpenTTD, Warcraft III, 7-Zip and the standalone test programs are not packaged.

## Credits and license

Built on [Wine-NX by danfromtico](https://github.com/danfromtico/wine-nx),
Wine, Box64, DXVK, Mesa/mesa-switch, libnx and devkitPro. The new project name
does not replace their authorship or licenses. See [THIRD_PARTY.md](THIRD_PARTY.md)
and [LICENSE](LICENSE). This is an unofficial project, not affiliated with
Konami or Nintendo.
