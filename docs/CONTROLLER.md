# Controller diagnostics

The reported symptom is a working Start button, d-pad and analog movement,
with ABXY ignored at the difficulty menu. The upstream keyboard fallback used
A/B as mouse clicks, X as Space and Y as F. That is a concrete mismatch with
this project's PES keyboard profile. Whether this was the path used in the
reported run still needs the new hardware log: working directions alone do
not prove that the game is using XInput.

The 0.1.3 hardware trace contained no XInput calls and showed every controller
button delivered as a keyboard key. Package 0.2.0 therefore supplies the tested
PC `settings.dat` under `C:\\users\\steamuser\\Documents` with PES's XInput
mode enabled and holds the runtime in
gamepad-only mode. The keyboard and mouse fallback cannot change Plus into
Escape or ZL/ZR into arrow keys while that mode is active.

## Mapping

The label on the Switch differs from the game's Xbox prompts. Use the physical
position, not the printed letter. In particular, the bottom **B** is Xbox **A**.

| Switch | XInput | Keyboard fallback |
| --- | --- | --- |
| B (bottom) | A | X, short pass |
| A (right) | B | D, long pass |
| Y (left) | X | A, shoot |
| X (top) | Y | W, through pass |
| L / R | LB / RB | Q / E |
| ZL / ZR | LT / RT | Z / C |
| Plus | Start | Escape |
| Minus | Back | Enter (menu confirm) |
| D-pad | D-pad | Arrow keys |
| Left stick | Analog left stick | Arrow keys beyond dead zone |
| Right stick | Analog right stick | Mouse cursor |

The keyboard profile is retained as an explicit diagnostic fallback, not a
replacement for full analog gamepad support. It assumes the game's default
keyboard bindings. The file
`drive_c/PES13/pes2013.keys.txt` overrides the compiled defaults; it is loaded
before the test screen and before input polling starts. No game save is
generated, edited or replaced. The public package supplies `settings.dat` in
Wine's Documents profile using the reviewed PC preset that enables XInput.

## Read-only check

Hold L + R while launching the existing NRO to display Controller Check.
For PERF34, set `controller_test=1` in `switch/pes13-nx/configuration.ini`.
Older packages accept `1` in `switch/pes13-nx/controller-test.txt` instead.
Press all four face buttons: each row should show DOWN, then retain YES under
SEEN. Move both sticks and check the shoulders and d-pad. Press and release
Plus to enter PES.
The existing console is used before Wine/Vulkan takes the screen; no second
NRO or additional forwarder is involved. `settings.exe` remains inaccessible
from the normal launcher.

This screen tests libnx input and the same mapping function used by the
native XInput backend. It does not call through the Windows DLL and cannot
confirm that PES accepts its replies. The in-game trace supplies the next
layer of evidence.

## Bounded game trace

Production ships with `controller_trace=0`, `controller_gamepad=1` and
`production=1` in PERF34. The build log must identify
`pes13-nx-0.2.0-vk1-production`. To capture a short input trace, temporarily
set `controller_trace=1` and restart. The older sidecar spellings remain
accepted as a compatibility fallback.

`[PES13-INPUT]` records have three sources, capped separately at 128 changes
each (384 event records and up to three limit notices). Repeated unchanged
states and raw analog jitter are not logged. Other XInput player slots do
not consume player 1's trace budget. The normal runtime heartbeat is separate.

| Source | `raw` | `value` | `mode` |
| --- | --- | --- | --- |
| `pad` | Switch held buttons (low 16 bits) | queued fallback key mask | 0 keyboard, 1 XInput |
| `xinput` | Switch held buttons | returned Xbox buttons; bits 16/17 = LT/RT held | 256 connected player 1, 0 disconnected |
| `key` | held fallback key mask | virtual key in low 16 bits; scan code in high 16 bits | Windows keyboard flags; 2 = key up |

A `key` record means a keyboard event was submitted to Wine, not that PES
accepted it. Switch B should produce raw bit `0002`; in XInput it becomes
`00001000`. In keyboard fallback it submits virtual key `58` (X). The native
test's final `face_seen=f` means all ABXY buttons were observed.

For hardware testing, use the shipped gamepad-only profile and try Switch B at
difficulty. Plus must behave as Start and ZL/ZR as triggers. Close from HOME
and retain the log before restarting because the log is overwritten. A
controlled fallback comparison remains available: set
`controller_gamepad=0`, `controller_keyboard=1` and optionally
`controller_trace=1`. Restore the shipped values for normal play.

The native Horizon software keyboard is technically available through libnx,
but bridging it safely needs a separate Win32 text-input path: detect the
focused edit control, open `swkbd`, then submit Unicode input on a Wine thread.
It is intentionally outside 0.2.0 so the first production controller build has
no additional applet or text-event behavior to destabilize the game.

Do not conclude that the whole game is fixed from a passing native check.
Confirm the menu and a match on hardware, including simultaneous movement,
passing/shooting and shoulders, before disabling diagnostics for a release.
