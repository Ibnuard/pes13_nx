# FEXTendo keyboard previews

The newer [grouped settings/input preview](FEXTENDO-INPUT-SETTINGS-PREVIEW.md)
adds configurable held shortcuts, a compact 252 px keyboard and grouped
launcher settings. Its install and test instructions supersede the v4
shortcut and half-height layout instructions below for that preview only.

Preview v4 adds live editing for custom game fields, with an English UI and
the existing controller helper sprites embedded in the NRO. It does not read
the game's previous text into another input field. Preview v3 delivered full
text on Switch, confirmed by the user, but appended it at the game caret.
V4 instead gives the player Backspace, Delete and cursor movement to edit
the actual game field. The user confirmed v4 works on Switch in an initial
trial on 2026-10-01. The full controller/reconnect matrix and frame-time
impact have not yet been verified on hardware.
All ten host, linked ARM64 and rendering checks passed for the packaged build;
the evidence records the exact ELF, NRO and feature-source hashes.
Those automated receipts retain `hardware_tested: false`; the user report
above is separate from their modeled platform checks.

## Preview v4: install and test

Back up the working v3 NRO, then copy the `switch` folder from
`dist/pes13-fextendo-keyboard-preview-v4.zip` to the SD root, replacing only
`switch/pes13-fex/pes13-fex.nro`. Keep the current NSP, FEX DLL, launcher
assets, presets, game files and saves. This preview retains the frozen
production-v1/launch-fix baseline; it does not update the CI runtime lock.

1. In **Master League -> Manager Name**, activate the name field. Hold
   **L1 + R1**, then click **L3 once**. For a horizontal single Joy-Con, hold
   **SL + SR**, then click its stick once. Release all controls after opening.
2. The player who opens the keyboard owns its controls. Use the stick or
   D-pad to select a key and **A** to press it. Touch typing is also available.
   **B** is Backspace, **X** is one-shot Shift, **Y** moves the panel between
   the upper and lower half, and **L/R** (single Joy-Con: **SL/SR**) moves the
   text cursor. All inputs use the existing horizontal normalization.
3. With the caret after `Nunu`, press Backspace four times, then type `Bejo`.
   Check the real game field as it changes. Reopen and change a middle letter
   with Left/Right/Delete. Also try repeated letters, mixed case and numbers.
4. **Enter** explicitly sends Enter to the game. Plus is its shortcut; the
   left single Joy-Con uses Minus. **Close** finishes already queued edits
   and hides the panel; it does not undo edits or implicitly confirm the
   game dialog. Full controllers also have Minus as a Close shortcut.
5. Try both players, full/paired controllers and either horizontal Joy-Con.
   Disconnect a session controller while editing: pending input is canceled
   and the existing reconnect/FEXTendo pause flow takes priority. After
   reconnect, the player must still choose **Continue**.

The overlay uses an ASCII/US key layout and does not implement a full IME.
Special character acceptance, Home/End/Delete behavior, automatic opening,
Switch layer presentation and frame-time impact must be checked on hardware.
Only detectable text-entry signals trigger auto-open; a game-drawn field can
still require the shortcut. Standard single-line Windows Edit controls keep
the native Switch applet's prefill/replace/Cancel behavior.

## Preview v4 implementation

The controller monitor owns a separate, half-height VI layer using the same
managed-layer helpers as the existing pause screen. It leaves the main game
surface alone. Font data is read from the existing launcher asset; sprites
are embedded from the supplied Solid Duo SVGs, with attribution retained in
`assets/README.md`. The layer redraws when keyboard state or display mode
changes, and releases its surface/font when closed. There is no keyboard
surface or rendering work while idle, and no new runtime log output.

The bounded 32-key queue shares the native keyboard mutex. Native applet and
overlay requests exclude each other. The owning Wine window thread consumes
one key transition per 50 ms pump interval, including separate Shift lead
and release intervals. It uses the same verified zero-success NTSTATUS path
as v3 and includes extended scan codes for cursor/navigation keys. Stale
tokens, lost focus, destroyed windows and reconnect cancel pending keys;
the Wine pump releases any injected key and Shift before acknowledging the
overlay's completion. During a pause the Wine thread may remain at its
existing wait boundary; input stays suppressed until it can finish cleanup.
The monitor then waits for both session controllers to become neutral.

Both XInput slots remain connected while the keyboard captures controller
input. Their packet numbers reflect suppression/restoration. A held opening
chord does not type or move the caret. Repeats are limited to navigation,
Backspace and cursor shortcuts, and a full queue is shown in the UI instead
of silently overwriting pending keys. A display setup failure cancels the
request without typing into the game or killing the game process.

Host ASan/UBSan tests exercise live replacement, middle edits, reopening,
controller ownership, horizontal normalization, touch, repeat/queue bounds,
focus/reconnect cancellation and native Edit coexistence. Linked ARM64 tests
exercise the shipped queue, Wine pump, status handling, scan codes and
XInput suppression. Render tests use the actual C drawing functions on a
1280x360 allocation with stride guards. These do not establish hardware
compatibility or game performance; all package receipts retain
`hardware_tested: false`.

## Existing-value editing: investigation

The current custom-field path starts the applet with an empty string and
injects the accepted result as keys. Only a standard Windows Edit control has
the read/prefill/replace path (`WM_GETTEXT`, `EM_SETSEL`, `EM_REPLACESEL`).
Sending `WM_GETTEXT` to a generic game window does not prove that its reply is
the text field: the default reply is the window title. See Microsoft's
[WM_GETTEXT contract](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-gettext).

The reviewed Winlator app source, commit
`3981d86efa4f333b2a34a7da8b6521476cd8c8b9`, opens Android's keyboard through
`AppUtils.showKeyboard`. `XServerDisplayActivity.dispatchKeyEvent` passes
input to `Keyboard.onKeyEvent`, which injects key presses/releases into X11.
Its key map includes Backspace, Delete, arrows, Home and End. This reviewed
path supports editing through keyboard commands; it does not fetch a custom
game field's existing value. Source:
[Keyboard.java](https://github.com/brunodev85/winlator-app/blob/3981d86efa4f333b2a34a7da8b6521476cd8c8b9/app/src/main/java/com/winlator/xserver/Keyboard.java).
DirectInput's [keyboard state](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee418261(v=vs.85))
contains key states, not the game's edited string.

For actual prefill of the native applet, an investigation would need to
determine whether Nama Manager exposes a real Edit child or implements
text-context requests such as
[IMR_DOCUMENTFEED](https://learn.microsoft.com/en-us/windows/win32/intl/imr-documentfeed).
That API requires application support and may return only surrounding text;
it cannot be assumed to return the complete field or provide replacement.
If PES does not expose usable text APIs, genuine prefill and replacement
would require access to the game's field state, such as a version-verified
game-specific hook. That is separate from general keyboard editing: the
Autorun approach below does not need to read the field or inspect the game
executable first.

For native prefill and replacement, the required behavior is to read the
actual active field and its identity, open the
native keyboard prefilled with `Nunu`, then replace it with `Bejo` only if
the same field and original value are still current. Use the verified game
editing path so its caret, length and change notifications remain consistent.
Cancel must not alter the field; switching fields or changing its value while
the applet is open must invalidate the operation. Reopening an unchanged
value must not inject a duplicate.

Remembering the last injected string alone is insufficient: the same game
window can contain different fields, the game can reject/limit characters,
and players can edit through other inputs. Blind Ctrl+A/Backspace cannot be
treated as verified replacement until the target field's behavior is tested.
The earlier investigation did not change the v3 artifact. V4 is built separately.

### Autorun: edit the game field live

Reviewed `autorunhq/autorun` at commit
`c889e4eb722ba6435e50500d9dde51f59781ce99`. Its
[floating keyboard interface](https://github.com/autorunhq/autorun/blob/c889e4eb722ba6435e50500d9dde51f59781ce99/horizon-wine/source/osk.h)
explicitly describes the same limitation encountered here: a completed string
from the modal Horizon keyboard does not provide live Backspace or cursor
movement inside a custom game field. Autorun supplies its own overlay and
sends individual key presses while the actual field stays visible in-game.
It does not retrieve or mirror the field's previous string.

The [keyboard implementation](https://github.com/autorunhq/autorun/blob/c889e4eb722ba6435e50500d9dde51f59781ce99/horizon-wine/source/osk.c)
provides letters, Backspace, Delete, cursor arrows, Shift, Space and an explicit
Enter. Events are queued with separate down/up timing: 40 ms key hold and
10 ms gap, with additional Shift timing. The
[Wine driver](https://github.com/autorunhq/autorun/blob/c889e4eb722ba6435e50500d9dde51f59781ce99/dlls/win32u/winnx_drv.c)
maps virtual keys to scan codes and sends them through
`NtUserSendHardwareInput` to the focused window. This makes the events
available to keyboard-state consumers such as DirectInput as well as ordinary
Windows message handling; acceptance still depends on the game.

For example, with the caret after `Nunu`, the player can send four Backspaces
and type `Bejo`, watching the field change directly. Simply typing `Bejo`
without deleting still appends it. Closing the overlay does not undo edits
already delivered. This differs from the native applet's confirm/cancel
transaction and must be reflected in the UI.

Automatic opening is a separate concern. The reviewed
[focus hook](https://github.com/autorunhq/autorun/blob/c889e4eb722ba6435e50500d9dde51f59781ce99/dlls/win32u/input.c)
checks for `edit` in the window class name when keyboard-on-text-focus is
enabled. Arbitrary game-drawn fields are not detected by that rule; a manual
shortcut remains available. The reviewed overlay uses a US key layout.
This is a general input mechanism, not evidence that every game, text field,
or language is supported.

This research informed the v4 implementation above. It implements live
editing using FEXTendo's UI/controller layer rather than importing Autorun's
renderer or changing the runtime baseline. The existing per-player shortcut,
horizontal normalization, two-controller connections, reconnect handling and
silent behavior are retained. Native prefill remains for verified standard
Edit controls. This is not evidence of an upstream or hardware compatibility
guarantee.

## Preview v3: complete text and one-click shortcut

`NtUserSendHardwareInput` is declared `BOOL` in the frozen Wine `ntuser.h`, but
`NtUserCallHwndParam_SendHardwareInput` in `dlls/win32u/window.c` directly
returns `send_hardware_message`'s `NTSTATUS`. Success is **zero**. V2 treated
zero as failure, aborted after its first event, and could leave that first
key or Shift pressed because it had not recorded a successful key-down.
V3 explicitly accepts zero and aborts on nonzero status, recording and
releasing each successful press before advancing to the next character.

Earlier host tests returned `TRUE` from the mocked API, hiding the mistake.
The new regression runs the actual linked ARM64 Wine text pump and
`NtUserCallHwndParam` dispatch with the server returning `STATUS_SUCCESS`.
It reproduces `hallo` becoming `h` with H left held in the v2 ELF; v3 delivers
the entire string and releases every key. Mixed case, repeated letters,
spaces, punctuation, Unicode, focus loss and a real error status are covered.
The host mock now follows the same NTSTATUS contract.

Manual custom entry also retains its target when transient IME/caret hints
change, including after the first character. Real focus/window changes and
reconnect still cancel delivery. Automatic detection keeps its eligibility
checks, and standard Edit replacement retains its existing guards.

The shortcut detects a new stick press on one controller while both shoulders
are held. It has no 0.75-second hold timer. Holding the stick does not repeat;
releasing and clicking it again works with the shoulders still held. The
same normalization supports P1/P2, full controllers, paired Joy-Con, and
either horizontal single Joy-Con without combining buttons across players.

## Preview v2: confirmation hang

The controller runtime uses `AlwaysSuspend`. With v1's interactive TextCheck
callback, the native keyboard asks the application to validate the confirmed
text while retaining foreground. The caller is suspended and cannot reply;
the keyboard cannot finish until that reply arrives. This matches the reported
keyboard remaining open at confirmation.

V2 temporarily selects `SuspendHomeSleep` before `swkbdShow`, then restores
`AlwaysSuspend` on both success and cancellation/error. HOME and console sleep
still suspend the application. Existing Wine input/frame boundaries wait while
the keyboard is active, leaving the native applet worker free to reply. HID
absence while the keyboard owns foreground does not initiate a spurious
reconnect; real controller state is checked again after the applet returns.

The regression executes the actual linked ARM64 `swkbdShow`, its interactive
storage processing, and our validation callback. With modeled Horizon IPC and
suspension rules, the v1 ELF reproduces the blocked confirmation and the v2 ELF
returns the validated text. Confirm, Cancel and focus-setup failure also check
restoration and gate release. Earlier tests stubbed `swkbdShow` and did not
model this protocol, which is why they missed this failure.

Sources: [libnx v4.12 software keyboard](https://github.com/switchbrew/libnx/blob/v4.12.0/nx/source/applets/swkbd.c)
and [libnx v4.12 focus handling](https://github.com/switchbrew/libnx/blob/v4.12.0/nx/source/services/applet.c).

## Preview v3: historical install and test procedure

Use the existing working production-v1/launch-fix installation with the two
controller preview. Back up its NRO, then replace only:

```text
switch/pes13-fex/pes13-fex.nro
```

The existing forwarder NSP, FEX DLL, launcher assets, game files and presets are
used. This is an opt-in NRO preview; it does not update the GitHub release or
approved CI runtime lock.

1. Open **Master League -> Nama Manager** and activate its text
   field. Watch whether the Switch software keyboard appears automatically.
2. If it does not appear, hold **L1 + R1 (L + R)**, then **click L3 once**.
   On a horizontal single Joy-Con, hold **SL + SR**, then **click its stick once**.
   Either connected player can invoke it. Release the buttons after it opens.
3. First enter `Hallo`, confirm the keyboard, release the controls and wait
   for the letters to finish appearing. Confirm/save using PES itself: closing
   the keyboard deliberately does not inject Enter or Start.
4. Check Cancel leaves the name unchanged. Then try `hallo`, `HaLLo`, spaces
   and punctuation. Accented letters can be tried separately; the game may impose
   its own character/font restrictions.
5. Check repeated entry, P1/P2 and horizontal controllers. Disconnect a
   controller while the keyboard is open: the pending text should be canceled
   and the existing reconnect/FEXTendo pause flow should take precedence.

A standard single-line Windows Edit field is prefilled and replaced on
confirmation. A custom game field cannot be read generically: the keyboard
starts empty and inserts at the game's current caret. It does not guess the
old text or send blind Backspace/Select All. Select/clear text within PES first
when replacing an existing custom name. Password, read-only and multiline Edit
fields do not trigger automatic opening in this preview.

Record separately whether (a) automatic opening worked, (b) the shortcut
opened it, and (c) the text reached PES correctly. A working shortcut does not
prove automatic detection. No text/input log is written.

## Native applet implementation boundaries (v3, retained for Edit controls)

The NX display driver's Wine event pump detects an eligible Edit focus, an
explicit IME-open plus composition rectangle, or a system caret belonging to
the focused window. Main-game focus alone does not open a keyboard. Detection
runs at most every 50 ms and only on the owning window thread. A field is
latched after confirmation/cancel to avoid immediate reopening. A custom UI
that exposes none of these signals needs the explicit shortcut until a
PES-specific trigger can be verified.

The Wine thread sends a bounded request to the native controller monitor.
That monitor opens `swkbd` with the existing shared applet mutex. It never
calls Win32 APIs. Reconnect takes priority; all controllers must return to
neutral before their input reaches the game. XInput slots remain connected
and their packet counters change when input suppression starts/ends.

Results return to the owning Wine thread. Standard Edit replacement checks
that the field still contains the original text. Custom fields receive ASCII
as keyboard scan codes, holding each press for one 50 ms pump interval and
releasing it before the next character. This reuses the keyboard route that
was used before XInput and allows DirectInput state polling to observe keys.
Other characters use `KEYEVENTF_UNICODE` packets. The Horizon keyboard backend
now preserves the complete UTF-16 unit and excludes these packets from raw
scan-code input, matching Wine's `VK_PACKET` translation. No Enter is appended.

Focus loss/destruction and reconnect cancel outstanding delivery and release
any injected key/Shift state. Automatic entry also cancels on IME/caret
deactivation; explicit manual custom entry stays bound to its window despite
those hint changes. The queue permits one
request/delivery at a time. Invalid UTF-8, unpaired surrogates, control
characters and strings exceeding the field's limit or 256 UTF-16 units are
rejected. Cancel does not inject anything.

API references: [libnx software keyboard](https://switchbrew.github.io/libnx/swkbd_8h.html)
and [Windows keyboard input](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput).
The implementation was checked against the installed libnx and the frozen
Wine sources, including Wine's `queue_keyboard_message` and `VK_PACKET`
translation. The game's acceptance still requires the hardware checks above.

## Reproduce preview v4

```sh
python3 tools/build-fextendo-gamepads.py --keyboard-overlay --output local/fex3/keyboard-v4
python3 tests/fextendo_keyboard.py local/fex3/keyboard-v4
python3 tests/fextendo_osk_binary.py local/fex3/keyboard-v4/native-build/wine-nx-runtime.elf --before local/fex3/keyboard-v2/native-build/wine-nx-runtime.elf --output local/fex3/keyboard-v4/overlay-test.json
python3 tests/fextendo_osk_render.py local/fex3/keyboard-v4 --assets dist/v3.6-fast-api-v1/switch/pes13-fex
```

Also run the retained native `keyboard`, `focus`, `controllers`, `hid-startup`,
`silent`, `startup` and `maintenance` linked checks against this same final ELF.
The v4 packager requires all ten matching receipts and source fingerprints.
The renderer's `--assets` directory must contain the existing `launcher/font.bin`.
The optional sprite regeneration tool needs Pillow and CairoSVG; the generated
header is checked in so a runtime build does not need those image libraries.

## Reproduce preview v3

```sh
python3 tools/build-fextendo-gamepads.py --keyboard --output local/fex3/keyboard-v3
python3 tests/fextendo_keyboard.py local/fex3/keyboard-v3
python3 tests/fextendo_keyboard_binary.py local/fex3/keyboard-v3/native-build/wine-nx-runtime.elf --output local/fex3/keyboard-v3/keyboard-test.json
python3 tests/fextendo_keyboard_focus.py local/fex3/keyboard-v3/native-build/wine-nx-runtime.elf --before local/fex3/keyboard-v1/native-build/wine-nx-runtime.elf --output local/fex3/keyboard-v3/focus-test.json
python3 tests/fextendo_keyboard_delivery.py local/fex3/keyboard-v3/native-build/wine-nx-runtime.elf --before local/fex3/keyboard-v2/native-build/wine-nx-runtime.elf --output local/fex3/keyboard-v3/delivery-test.json
```

The linked test needs Unicorn and pyelftools, like the existing controller and
production regressions. Run those regressions on the same final ELF before
packaging. `tools/package-fextendo-keyboard.py` verifies the final ELF/NRO,
source fingerprints and all nine test receipts before creating the archive.

Host ASan/UBSan tests execute the actual queue, detection and delivery code
with platform APIs modeled, round-trip every permitted Unicode scalar, and
exercise cancel, limits, stale focus, held input, reconnect and key release.
The linked ARM64 test executes the real native applet monitor with libnx/HID
services modeled. Existing linked controller, HID startup, silent logging,
launch-fix and maintenance/affinity checks cover the retained baseline.
These tests do not run PES13, emulate a real Switch applet, or establish that
every profile/save dialog exposes a detectable text-entry signal.
