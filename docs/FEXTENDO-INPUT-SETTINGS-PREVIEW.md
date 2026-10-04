# Grouped settings and input preview

Local preview based on main `870ba1f` and the pinned `runtime-keyboard-v4`
source archive. This is a hardware-test build; it does not promote a new
production release or change `release/runtime-lock.json`.

## Install

Copy the `switch` folder in `dist/pes13-fextendo-input-fix/` onto the SD root.
Only `switch/pes13-fex/pes13-fex.nro` is included. Keep the existing launcher
assets, presets, renderer DLLs, FEX DLL, game and save files. No ZIP is needed.
The package's `rollback` folder contains the pinned keyboard-v4 NRO; copy
its `switch` folder instead if this local build regresses on hardware.

## Settings navigation

- **Graphics preset** opens Medium, Low, Extra Low and High choices.
- **Renderer** opens the existing Default DXVK and GPL Async choices.
- **Keyboard** opens **Shortcut** and **Position** submenus.
- **Audio** opens menu-sound and launcher-music switches.
- **Debug timestamp** remains a switch on the Settings root page.

Press A to open a group or apply a choice; B returns one level. Entering a
group alone does not change its setting. The selected choice is highlighted
on entry. Failed storage writes do not update the displayed selection.

Keyboard shortcut choices: L + R + Left Stick, Plus + Minus, L + R + Plus,
ZL + ZR + Minus, or Disabled. Hold the full combination for **600 ms**.
Horizontal single Joy-Cons use SL + SR + Stick for any enabled choice.
Disabled turns off the manual shortcut; detectable text fields can still
open automatically. Preferences are saved in `launcher/keyboard.ini` with
backup recovery for an interrupted save.

The custom keyboard is **252 px tall at 1280x720**. The title and explanatory
footer have been removed. Settings chooses its initial Top/Bottom position;
Y still moves it while typing. Touch coordinates and docked layer sizing
use the same compact height. Enter confirms; Close keeps edits already made.

## Controller fix

Previously a complete shortcut chord set a global input-suppression latch,
even when no keyboard opened. Releasing that latch required both players'
buttons and sticks to become neutral. That is a concrete path to live video
and audio with temporarily unresponsive controls; it is not proof that all
reported hardware stalls have that cause.

The new detector only queues a request after the hold threshold. Requests
alone do not suppress XInput; actual keyboard capture still does. An
unconsumed request expires after one second. Chord rearming depends on that
player releasing the combination, not on analog motion or the other player.
Focus loss, reconnect and active keyboard states inhibit shortcut detection.

## HIGH transition freeze: evidence still needed

The user reports the freeze with both renderers. This preview **does not
claim to fix HIGH freezes or implement a replay-only 30 FPS cap**. Global
`d3d9.maxFrameRate` would also cap gameplay, and no verified PES replay-state
hook has been identified. Existing graphics and timing presets are retained.

For one reproduction, copy `optional-high-diagnostics/switch` from the
package onto SD as well. It adds `launcher/diagnostics.txt` containing `1`.
Run HIGH with the renderer that previously froze, then collect
`switch/pes13-fex/transition.log`. The next run retains one
`transition.previous.log`. Remove `launcher/diagnostics.txt` afterwards.

This opt-in worker records frame count/errors, age of the last frame,
process memory, native heap use/free and the keyboard-input gate every two
seconds, for at most 20 minutes. It writes nothing from Present or XInput.
Elapsed time starts after the first game presentation, after the launcher.
When disabled it reads the marker once and performs no diagnostic writes.
This is coarse evidence, not a GPU profiler or a complete crash dump.

## Verification and limits

The package carries build/test receipts and SHA-256 hashes. Host checks use
ASan/UBSan for navigation, saved choices/recovery, shortcut handling, keyboard
delivery, compact rendering/touch bounds and diagnostic limits. Linked ARM64
checks execute controller/keyboard paths with modeled Horizon services.
Screenshots use the actual C renderer. No Switch hardware run is claimed.

The builder reconstructs and verifies all eight keyboard-v4 generated source
hashes before applying this change. FEX adapters come from the frozen archive;
the FEX DLL is not rebuilt or shipped. Native libraries are linked from the
local WSL SDK/Mesa installation. Their binary hashes differ from the original
macOS production environment; `evidence/dependency-diff.json` records this.
Therefore this NRO is a local preview, not an identical production binary
with only UI bytes changed. The approved runtime lock remains unchanged.
