# PES13 Settings Debug

This developer-only NRO opens the user's original `C:\PES13\settings.exe`.
It shares the installed `switch/pes13-nx` runtime and registry with the game.
It is excluded from the normal single-NRO runtime package.

Copy `pes13-settings-debug.nro` to `switch/pes13-nx/` and your own
`settings.exe` to `switch/pes13-nx/drive_c/PES13/settings.exe`.
Create a separate Sphaira forwarder to
`sdmc:/switch/pes13-nx/pes13-settings-debug.nro` using the same 32-bit,
no-alias, four-core configuration as the working game forwarder.
Close the game before opening Settings Debug.

The first hardware log showed a dynamic load failure for RICHED20.DLL and
an attempted settings path of `C:\KONAMI\Pro Evolution Soccer 2013\settings.dat`.
Copy the entire updated debug package's `switch` directory, including the
RichEdit dependency and the PC preset at `drive_c/KONAMI/Pro Evolution Soccer 2013/`.
This observed Settings.exe path supersedes the earlier inferred Documents path.
Whether the game uses the same path still needs a hardware check.

Use the touchscreen to select tabs, controller mode and the OK button.
Joy-Con is exposed through XInput without controller-to-keyboard events.
If Settings.exe offers a controller preview, test buttons and sticks there.
This is an actual Windows application; available test controls depend on it.
Hold L+R at startup for the separate native Controller Check if desired.
The native check alone does not prove Settings.exe received XInput.

Select XInput and press OK to save. Settings may exit after saving; close the
runtime from HOME and launch the game again. Saving can change game graphics
and controller preferences because this tool deliberately uses the same profile.

Return `switch/pes13-nx/pes13-settings-debug.log` after the test.
`[PES13-SETTINGS-FILE]` reports attempted Windows paths, resolved SD paths,
requested access, creation disposition and NTSTATUS, capped at 128 records.
`status=00000000` means the open/create operation succeeded; a writable open
does not alone prove a completed save. Confirm the resulting file on the SD.
`[PES13-INPUT] xinput` records indicate Settings.exe polled the native backend.
Input changes remain capped at 128 per source; general verbose logging is off.

Build from WSL with the same prepared production build tree:

```sh
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-settings-debug.py
```

Do not run other builds against that tree at the same time. The builder saves
the production source and linked outputs, applies diagnostic changes, builds
the separate NRO, and restores the originals in a finally block. The diagnostic
source copies are retained under ignored `local/settings-debug-source/`.
