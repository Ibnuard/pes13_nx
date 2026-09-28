# Archived project notes

Historical notes moved from the root README on 2026-09-28. Build names, test
results and installation paths below describe their respective older snapshots;
use the root README for the FEXTendo directory layout. These notes are not a
statement of current performance.

---

# PES13-NX

Latest FEX experiment: [read-only PES timing audit and batched diagnostics](FEX3-TIMING-AUDIT.md).
The Fast-vector device test still shows accelerated motion and poorer camera
pacing than Fastest. `dist/pes13-fex3-timing-audit/` selects the existing Fastest
profile, removes per-line SD flushes during periodic reports, and samples
PES's own timing/frame-skipping state every five seconds. It does not yet
claim to fix the 2x motion or sustain 30 FPS. The folder contains one NRO and
its paired dependencies, without a ZIP. The prior
[Fast-vector](FEX3-FAST-VECTOR.md) and
[Fast/Control comparison](FEX3-SPEED-PRESETS.md) packages are preserved.

PES 2013 PC on Nintendo Switch, using a custom PES13-NX Horizon runtime built
from Wine-NX/Wine, Box64's ARM64 dynamic recompiler, and Direct3D 9 through
DXVK + Mesa NVK. Upstream credits and licenses are listed in [THIRD_PARTY.md](../THIRD_PARTY.md).

The `experimental/fex-core` branch starts a [FEX port for Horizon](FEX2-BRINGUP.md).
The FEX1 JIT adapter probe passed on Switch. FEX2 now connects the ARM64 WOW64
module to Wine, adds an exception bridge and supplies an original x86 test in
a separate package. The compact-heap build has now
[passed its complete x86 guest test on Switch](FEX2-RESULT.md), including
SSE, x87, executable-code invalidation and one worker's TLS isolation and exit.
The native register/exception, heap, physical-counter and callback ABI
preflights also pass. [FEX3](FEX3-INTEGRATION.md) adds isolated concurrent
fault stacks, Wine guest exception dispatch and one NRO with stress-test/PES
modes in `switch/pes13-fex/`. Its first device stress test failed at automatic
code modification (worker result `0x10`); subsequent fixes are documented below.
The memory fix reduced per-thread lookup reservations from 152 to 25 MiB and
commits pages in bounded chunks. Its device run has no logged allocation
failures: all four workers pass the first automatic code change, then time out
at their first guest exception. Native concurrent faults pass. The subsequent
trace reaches ARM64 PE exception dispatch with zero x86 handler entries.
Local binary tests reproduce an unwind loop caused by PE Wine's missing
bootstrap module index. The FEX3 unwind-fix shares the live native/PE index,
uses Wine's tree operations on both sides and checks unwind metadata at boot.
The unwind-fix device run now passes one complete worker wave, including
64 automatic code updates and 64 handled guest faults. It then fails a 64 MiB
reservation while starting the next wave. The new reserve-fix NRO repairs
conflict recovery and supplies the self-thread object query that FEX needs
to release its per-thread state. The reserve-fix now [passes the complete
four-wave stress test on Switch](FEX3-RESULT.md): 16 workers, 256 automatic
code updates, 256 handled guest faults, lifecycle PASS and process exit code 0.
The first subsequent PES run fails a 64 MiB heap reservation. The aligned-heap
fix removes padding and gets PES further: a Vulkan surface and compiler
threads initialize, then another 32 MiB heap reservation fails and parks a
thread, leaving a black screen. The subsequent `pes13-fex3-compact-heap` build
uses 8 MiB spans with smaller allocator pages; blocks above 2 MiB use direct
mappings. Local binary tests cover fragmented space, 350 allocation boundaries,
realloc, thread-heap reuse and exceptions. Its PES device run reaches many
game workers, then another 8 MiB reservation fails. The
`pes13-fex3-compact-cache` candidate removes the unused L2 reservation when
L2 is disabled (the pinned default), reducing lookup address space from
25 to 1 MiB per thread. L1 capacity/policy and guest addressing stay intact.
Local tests cover 32 live caches, lookup targets, invalidation and L1 resizing.
The next two device runs confirm that fix is active but still exhaust guest
address space. One faults in the IR emitter after a failed 16 MiB scratch
allocation; the other stops on an 8 MiB heap reservation. The
`pes13-fex3-scratch-reuse` build reuses disowned compiler buffers before
growing their shared pool, retaining their full capacity and atomic ownership
checks. Previously, idle buffers could stay pinned for five seconds. It also
rejects failed allocations before publishing a null buffer. The user reports
complete stress PASS and a first PES loading frame, followed by an intermittent
startup stall. The `pes13-fex3-fd-routing` NRO fixes a locally reproduced
native server race that could exchange different threads' startup pipes.
It consumes transferred descriptors by their protocol identity and wakes all
keyed waiters. The user now reports frames in both attempts. The supplied log
reaches successful Vulkan presents, then stops when the shared executable JIT
buffer grows from 32 to 64 MiB: Horizon returns `0xdc01` (invalid memory range).
The JIT-growth candidate retries smaller fresh code buffers and records the
actual capacity, preserving references to older live code. The subsequent
startup-probe log confirms DXVK presents, then native RW alias searches fail
for 64, 32 and 16 MiB buffers; FEX stops allocating and parks that thread.
The `pes13-fex3-small-cache` build tries down to 2 MiB and gives the native
handle table 64 slots. Its PES run avoids the terminal allocation failure,
but repeated 8/4 MiB code-cache rollovers coincide with a near-stall in
Vulkan presents. The early 64 MiB cache, native compiler scratch and rejected-
suspend backoff subsequently allow the intro to appear, according to the user.
The native L1 update removes that `FindBlock` failure, but the latest device
log still shows a choppy intro followed by 4/2 MiB executable-cache allocation
failures and parked threads. The early 128 MiB code-buffer update now reaches
the PES menu on Switch. Loading team selection then exhausts guest address
space, Vulkan allocations fail, and the main thread exits with `c0000005`.
The preceding FEX3 candidate reduces the per-thread
CALL/RET prediction cache from 4 MiB to 256 KiB, retaining its guard recovery
and the successful 128 MiB initial code buffer. It saves 127.5 MiB across 34
live prediction stacks in the linked ARM64 allocation model. Local lifecycle,
guard recovery and exception tests pass; this candidate still needs a Switch
test. The subsequent alias-perf control and same-core scheduler tests still
hang at team selection. The latest log records guest-VA exhaustion, Vulkan
allocation failures and a `c0000005` exit. [The native-heap candidate](FEX3-FAST-NATIVE.md)
moves FEX-private CRT/container allocations to native memory and adds explicit
Fast (x87 64-bit) and Fastest (also relax scalar TSO) profiles. Both require
the paired ABI-3 NRO/DLL. Device testing confirms the memory improvement but
both presets remain too slow at team selection. [The final FEX attempt](FEX3-FINAL-3D.md)
removes an injected suspend delay, fixes stale writable-code tracking, batches
checks in static game/renderer text, and reserves a spare JIT generation early.
It requires the matched NRO, FEX DLL and ntdll.dll. The tester now reports much
faster 2D but a team-selection hang. [The team-sync candidate](FEX3-TEAM-SYNC.md)
restores scalar/SIMD/string ordering in Fast and captures bounded thread evidence
only when presentation stops. Its device run freezes in the intro; new counters
identify hundreds of thousands of rejected self-suspend requests. The
[self-suspend candidate](FEX3-SELF-SUSPEND.md) implements a blocking self
request in the native server, preserving suspend counts until resume, and
restores the earlier Fastest configuration. Local concurrent and linked ARM64
tests pass. The tester now reports reaching a match at visually around 30 FPS,
with a few remaining bugs. This is the [current checkpoint](FEX3-CHECKPOINT.md);
stable measured 30 FPS and a controlled comparison with Box64 remain unverified.
The follow-up [frame-pacing candidate](FEX3-FRAME-PACING.md) restores the
Box64 package's DXVK limiter setting and adds native frame-gap measurements
for the reported brief pauses and apparent speed bursts during kick-off.
It is delivered as a copy-ready folder without a ZIP; device validation is
pending and the self-suspend checkpoint remains available.
The established game runtime still uses
Box64 on the main branch; this branch retains the working FEX checkpoint.

Hardware testing has reached matches at 1280x720 with XInput gamepad control.
The experimental PERF27 runtime improves notification routing, while earlier
changes specialize translation of measured PES CPU hotspots. Recent match
segments measure about 15–19 successful presents/s; smooth 30 or 60 FPS match
play is not established. Replay/transitions still stutter and intermittent
startup crashes remain. [PERF28 sampling](PERF28-RESULT.md) identifies a
saturated translated game worker; [PERF29](PERF29.md) tests scoped block
growth with a same-NRO control. The stall also reproduced with growth disabled;
[the fresh PERF30 audit](PERF30-RESULT.md) finds a busy game worker and
incomplete driver timing coverage. The [PERF31-labelled uploads](PERF31-RESULT.md)
actually ran PERF25 because a settings-only overlay retained the older NRO.
[PERF32](PERF32.md) tests larger translated game blocks on the PERF25 base;
every variant includes its NRO. Its [first result](PERF32-RESULT.md) still
shows long sections around 12 presents/s; the log ends at the reported corner,
before the subsequent slowdown is captured. A 30 FPS match and a startup fix
remain unproven. Menus running near 60 FPS
do not establish match performance or full-match compatibility.

The earlier [PERF33 fastmath](PERF33.md) experiment keeps the
same renderer and startup path but scopes `FASTNAN=1`, `STRONGMEM=0` and
`FORWARD=1024` to newly translated game blocks after the first present. This
is an intentionally aggressive CPU experiment; use its same-NRO control or
the PERF32 package if ordering or stability regresses. No 30 FPS result is
claimed until a matched Switch run confirms it.

The configuration migration is [PERF34 CONFIG](PERF34.md). It keeps
the PERF33 runtime and replaces the collection of root-level `0`/`1` files
with one `switch/pes13-nx/configuration.ini`. Existing sidecar files remain a
read-only fallback inside the runtime, so older SD layouts still boot. The
PERF34 ZIPs do not ship those boolean sidecars; use the `config` variant for
the tested profile, `control` to disable PERF33 blocks, or `diagnostics` to
enable the profiler. This is a configuration migration, not a new FPS claim.

The latest hardware candidate is [PERF38 region fusion](PERF38.md), based
on the [PERF37 instruction samples](PERF37-RESULT.md). It reduces redundant
x87 rounding setup in eligible regions of measured math blocks while retaining
the existing DXVK and Box64 preset. Host tests pass; Switch performance is
unverified. The quiet package includes one NRO and supports a same-NRO control
through `perf38_region_fusion=0`. No stable 30 FPS gameplay result is claimed.
Its [first Switch run](PERF38-RESULT.md) confirms the optimization was
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
input tracing is off. See [controller diagnostics](CONTROLLER.md) for the
mapping, production settings and the optional diagnostic switches.

## Build and repository layout

Build natively in WSL; see [the build guide](BUILD.md). There is no Docker
requirement. Source revisions and toolchain versions are recorded in
[dependencies.json](../dependencies.json).

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
does not replace their authorship or licenses. See [THIRD_PARTY.md](../THIRD_PARTY.md)
and [LICENSE](../LICENSE). This is an unofficial project, not affiliated with
Konami or Nintendo.
