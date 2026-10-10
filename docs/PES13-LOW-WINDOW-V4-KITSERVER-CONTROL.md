# PES13 Low Window v4 — Kitserver comparisons

**0.3.9-lw4** provides two independent comparisons for the reported 2x
simulation speed and long on-field prematch loading. These are experimental
controls; neither issue is claimed fixed until tested on the Switch.

## First comparison: whole Gameplay Tool disabled

1. Close PES with HOME → X. Copy this package's top-level `switch/` to the SD
   root, replacing only `/switch/pes13-fex/pes13-low-window.nro`.
2. Use the same **PES13 Low Window** tile and **FEXTendo Memory v1 TEST** boot
   entry. No new NSP, kernel update or additional reboot is required.
3. Choose **Debug launch**, keeping preset, renderer, clocks, teams and stadium
   unchanged. The log should show `0.3.9-lw4` and
   `[LW4-KITCONTROL] Gameplaytool=disabled`.
4. Record the wait from entering the stadium to kickoff and whether the
   players, ball and match clock still accelerate. Save `fex-runtime.log`
   after closing. A failed attempt to load this optional DLL in the debug log
   is expected; the game loader's failure branch has been inspected.

LW3's plugin.ini test disabled only `plugin/gameplay.dll`. Its parent
`Gameplaytool.dll` and `camera.dll` still attached. LW4 disables the parent
using Wine's ordinary DLL load policy. Parent-dependent gameplay/camera/tool
features will be absent during this comparison. Kitserver's kit, face, ball,
AFS, stadium and other asset modules remain enabled.

This does not rewrite the game EXE, any DLL, settings.dat, saves or controller
bindings. Existing `plugin.ini` from the previous test may remain. Presets
still apply verified Frame Skipping OFF, VSync ON and XInput ON. No FEX,
DXVK, FPS cap, clock scaling or memory allocator retuning is included.

For a same-NRO comparison, add `kitserver_gameplaytool=1` under `[runtime]` in
your existing `configuration.ini`, fully close and relaunch. Do not create a
second conflicting key. `0` or absence disables the parent again. The exact
LW3 NRO is also supplied under `rollback/switch/`. Restoring LW3 removes the
new policy, irrespective of that LW4-only setting.

Normal Launch keeps native diagnostic logging disabled. Debug launch uses
the existing logs and counters. No continuous worker was added by LW4.

## Second comparison: duplicate face modules

Run this separately, after noting the first comparison. Copy the `switch/`
folder inside **`loading-control/`** to the SD root. This replaces only:

`/switch/pes13-fex/drive_c/PES13/kitserver13/config.txt`

It comments out `dll = fserv_3` and `dll = fserv_4`, retaining the primary
`fserv.dll`, one copy named `fserv_2.dll`, all asset-directory options, and
all other module entries. No face/hair files or mapping files are removed.
The three numbered DLLs in the inspected patch are byte-identical, and the
device log confirms they were mapped and attached at separate addresses.
Whether removing the duplicates improves loading or affects this patch's
face selection still needs a hardware comparison. Check both teams' faces,
hair and kits as well as the loading time.

Use this config only with the inspected ISN patch configuration; if you have
since changed the selector/stadium/config, comment those two entries in your
current file instead of replacing it. Back up the SD copy first. Restore the
original supplied config from `loading-rollback/switch/` if needed. Binary
NRO rollback and config rollback are independent.

## Evidence and limits

The latest input log SHA-256 is
`13c35ceff4d7f8037ce79c2d6db7f6b756506b9443dd112ec52618b24454a5bc`.
Its 61 live WECF flag samples retain Frame Skipping OFF; 60 include a valid
CRC report and one line is truncated before that field. Observed QPF/QPC
callsite targets still point at Wine's original kernel32 exports. These are
snapshots, not measurement of returned timer rates or the engine's private
timing object. They do not disprove the user's observed 2x simulation.

The optional `plugin/gameplay.dll` is absent from that run, but parent
Gameplaytool and its camera plugin still load. The user's observation that
the problem began with Kitserver motivates the parent-level comparison.

The earlier prematch/loading interval shows a busy file-callback worker even
while SD reads and shader creation are low. It does not identify an exact
asset or hot function. Reference Kitserver source recompresses generated
kit/font/number bins; however, executing the actual supplied DLL callsites
confirms **compress2 level 0 already**, including ballserv. No zlib change is
included: lowering a default level would not affect these calls, and level 1
would add work. `evidence/compression-audit.json` records the executed sites.

Local checks run the delivered ARM64 helper and Wine override parser with
modeled OS services, plus existing low-window memory/logging checks. They
cover case/path matching, other-DLL preservation, restore mode, environment
errors and normal-launch diagnostic silence. Existing unchanged host-test
receipts are explicitly labelled as reused. These checks do not certify
Switch gameplay, face rendering or a loading-time improvement.

See `evidence/analysis.json`, `evidence/loading-control.json`, build/test
receipts, source and SHA256SUMS.txt. No ZIP or game binaries are distributed.
