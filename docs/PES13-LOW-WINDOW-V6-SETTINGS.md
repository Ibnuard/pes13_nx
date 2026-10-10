# LW6: read the launcher preset from renamed patch paths

The supplied LW5 log reaches gameplay but shows that the patch did not read the
launcher preset. The launcher verified three CRC-valid files at 1.186–1.188 s:
flags `0289`, VSync on, frame skipping off and XInput on. At 8.891 s, Wine failed
to open `\KONAMI\FIFA World Cup 2026 Patch\settings.dat` with `c000003a`
(missing path). The live settings later reported `02c3`, frame skipping on,
XInput UI off and High quality instead of the selected Medium quality. The live
CRC was invalid, so those snapshots are evidence only, never a basis for poking
the guest's memory.

## Change

- The PES-specific Wine path resolver maps renamed patch `settings.dat` files to
  `C:\KONAMI\Pro Evolution Soccer 2013\settings.dat` before checking whether the
  patch directory exists. The canonical file remains managed by the launcher's
  preset transaction. Read, write and name-based metadata operations use the
  same real file, including normal permission, sharing and missing-file errors.
- Matching is limited to absolute C: paths under `KONAMI/<patch>/settings.dat`,
  `PES13/KONAMI/<patch>/settings.dat`, or
  `users/<user>/Documents/KONAMI/<patch>/settings.dat`. Wine first resolves normal
  DOS paths to NT paths. Root-handle-relative native requests, other drives,
  directory opens, original preset paths and all other files keep normal lookup.
- Both XInput selection flags (`0x0008` UI and `0x0200` runtime) are enforced,
  alongside VSync on and frame skipping off. Custom control bindings and
  unrelated flags remain intact. The preset transaction still verifies CRCs,
  rolls back failed writes and skips writes when nothing changed.
- Debug launch reports up to eight `[LW6-SETTINGS] alias=...` mappings. Normal
  launch performs no new diagnostic writes or log formatting. Routing requires
  no directory scan, extra worker or per-frame operation.

The patch's `OPTION.bin` and `EDIT.bin` remain in its own save directory. There
is no redirection of a whole KONAMI folder, no bundled settings replacement and
no need to delete saves. Game EXE/DLLs, Kitserver modules, FEX, DXVK, clock policy
and the low-window memory implementation are unchanged from LW5.

## Validation and limits

Sanitizer checks cover renamed paths, DOS prefixes/case, Unicode names,
nonmatching saves, allocation ownership/failure and bounded debug reporting.
The four-preset test verifies both XInput bits, frame skipping off, CRCs,
binding preservation, no-change writes and failed-transaction recovery.

An ARM64 control test executes the old LW5 resolver and reproduces `c000003a`
with the canonical preset present. The candidate test executes Wine's real
resolver and public read/write opens from the delivered ELF, with allocation,
filesystem metadata/handle creation and charset services modeled. It checks
successful alias resolution plus missing-file, missing-directory, allocation
failure and existing-file create errors. The low-window ARM64 regression suite
checks startup/memory admission, backing-store recovery and normal/debug gates.

These checks do not run PES or prove gameplay speed/controller behavior on a
Switch. The next device run must confirm that the alias appears, the missing
settings-path error disappears, and the live/game settings follow the launcher.
This build does not claim to fix every cause of stutter or Kitserver speed changes.

## Copy and test

1. Close the game. Copy only the package's `switch` directory to the SD root,
   replacing `switch/pes13-fex/pes13-low-window.nro`.
2. Keep the existing low-window forwarder/Atmosphere and runtime/game folders.
   No new NSP, KIP, INI or Kitserver configuration is included.
3. Select the intended graphics preset, then use Debug launch for the first test.
   Check controller behavior and match speed. The log should contain
   `[LW6-SETTINGS]` pointing from the patch name to the original preset path,
   `[SETTINGS-VERIFY] ... frame_skip=0 xinput=1`, and live settings matching the
   selected quality. Normal launch remains available without diagnostic logs.
4. If necessary, `rollback/switch` restores the exact LW5 NRO. User data is not
   replaced by either folder. Save the new `fex-runtime.log` for comparison.
