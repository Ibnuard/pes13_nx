# PES13 original: FEXTendo 39-bit branch

Release checkpoint: **v0.4.0**. The installation-checker/GUI hotfix uses version
`0.4.1` in the launcher display, NRO metadata and copy-ready package.

`pes13-39bit-patch` starts from `main` commit
`65f6962` and the approved original production runtime `0.3.8-r6`.
It does not use the Kitserver/patch-release runtime.
The generic Wine commit rollback fix is backported independently: a failed
backing allocation/map retains its original guest reservation and can be retried.
The stock r6 failure was reproduced before applying that fix.

## One forwarder, two automatic modes

Install one `PES13-FEXTendo.nsp`, targeting the single
`/switch/pes13-fex/pes13-fex.nro`. The game and its save folder do not change.

| Active boot environment | Mode selected by the same NSP | Graphics |
| --- | --- | --- |
| Ordinary Atmosphere | 32-bit no-alias | Low/Medium |
| FEXTendo Patch 1.0.0 | 32-bit no-alias (compatibility fallback) | Low/Medium |
| FEXTendo Patch 1.1.0 with `fxtauto-v1` | 39-bit low-window | HIGH available after live mapping probes pass |

The NPDM requests ARM64 with **32-bit no-alias**, no system-resource pool. Its
optional 32-byte ExeFS `/fxtauto` descriptor is ignored by stock and v1 loaders.
The updated FEXTendo loader validates the descriptor, promotes the process flags
to 39-bit plus the existing low-window request, supplies the established 16-MiB
system-resource pool, and only then calculates ASLR and creates the process.
There is no attempt to change an already-running process's address width.
The old `/fxtmem` contract still works for existing games/forwarders. No Title ID
allowlist is used, and ordinary applications without either marker are unchanged.
Both markers present, malformed markers and incompatible NPDM flags are rejected.

The adaptive hbloader checks its actual kernel layout before mapping the NRO.
In 39-bit mode it reserves the guest window and places native code above 4 GiB.
In 32-bit mode it uses ordinary native mapping and bounds the handoff heap to the
kernel's heap region. No SD file is treated as proof that a patch is active.
Wine's x86 guest remains 32-bit. Physical memory is still limited by the kernel's
process allowance; this does not promise 4 GiB of usable RAM or higher FPS.

## Install the copy-ready overlay

1. Copy the package's `switch` folder to the SD root. Back up the old NRO if a
   rollback is wanted. Game files/saves are not included or modified.
2. Install `forwarders/PES13-FEXTendo.nsp`, replacing the installed tile. It keeps
   Title ID `052d1913f51f5000`, names all 16 languages **PES13-FEXTendo**, and raises
   the CNMT revision to `131072` (`65536` in r2). Renaming an NRO alone cannot
   update an installed NSP target or HOME name.
3. Open **PES13-FEXTendo** from HOME. Without the updated patch, Low/Medium works
   through the same tile. An old `pes13-39bit.nro` can be removed after replacing
   its forwarder; the canonical game NRO is `pes13-fex.nro`.
4. For automatic 39-bit/HIGH, use the separate **FEXTendo Patch 1.1.0** installer,
   install its supported bundle, and reboot once through its Hekate entry. Simply
   copying the installer or boot files does not activate the loader. This update
   supports the pinned Atmosphere 1.11.2 revision, with official HOC 2.5.1 defaults.

Only the game has one NRO/NSP; the separate maintenance NRO updates FEXTendo Patch.
Do not install individual loader/kernel files into a different boot environment.
The patch update retains the previously tested kernel byte-for-byte and changes
the loader. This new automatic path still requires on-device validation.
Ordinary 36-bit/39-bit or alias layouts cannot enter Wine. Use the supplied HOME
tile rather than a generic Homebrew Menu launch.

## Automatic startup checks (0.4.1)

After an embedded FEXTendo splash, a blocking GUI popup checks the game
location, its PE32 executable and game data archives, then verifies 221 immutable
runtime files by size and SHA256. The runtime catalog includes Wine/FEX,
NLS/fonts, bundled renderer sources, launcher artwork and graphics templates.
Missing or changed runtime files are downloaded automatically from the pinned
official `v0.3.8-r9` asset. The complete ZIP and each staged member must match
the checksums compiled into the NRO. Game/Kitserver files, active renderer
copies/configs, saves, registry, preferences and the NRO are not repair targets.
An existing interrupted repair is recovered before checking again.
The startup font/logo are built into the NRO, so missing SD artwork cannot
prevent the repair popup from opening. One UI thread owns the framebuffer;
the main thread performs verification and repair while the popup keeps drawing.

The game check requires the 16 shared archives `dt01`â€“`dt04`, `dt06`â€“`dt0f`,
`dt10` and `dt11` under `img`, plus at least one usable `dt00_*.img`
commentary archive and one `dt05_*.img` menu-language archive. The two languages
can differ. The reference installation uses `dt00_e.img`; requiring `dt00.img`
in 0.4.0 was incorrect. The hotfix reads AFS directory tables and verifies
nonempty entries against each archive's actual length. File sizes and entry
counts can vary with language and mods. This is structural validation, not a
payload checksum or a requirement for PC settings, saves or optional videos.

A healthy installation works offline. Successful checks write a small functional
receipt at `launcher/startup-verified.dat`. Later launches do a few metadata reads
and reuse that receipt, skipping the full archive/runtime scan. A changed checker
revision, runtime catalog, installation anchors or pending repair journal forces
a new scan. This cache is not a full integrity check on every subsequent launch:
it cannot detect all manually edited/deleted runtime members. **Settings â†’
Maintenance â†’ Check runtime** forces verification and clears an old success first.
No periodic scan or automatic diagnostic logging runs during gameplay.
Repair needs Wi-Fi, a correct system date and approximately 300 MB free on SD.
The active modal cannot be dismissed into Play or Settings. On failure, A
retries; B or Plus closes the launcher. HOME/app shutdown cancels work safely. Allow an
installation commit to finish before powering off.

The boot status comes from the running process's kernel layout and low RX/RW
mapping probes, not the presence of patch files on SD. HIGH is unavailable
unless the 39-bit low-window preflight passes. A saved HIGH selection falls
back to Medium with an explanation; selecting HIGH and launching it are both
guarded. This admission check runs on each boot even with a cached file check.
The checker never opens a console. The launcher releases its framebuffer before
the game takes over.

## Resolved asset investigation

The owner confirmed that the kickoff blackscreen came from bad `dt09` data.
The temporary ALLOC32/ASSET read/FD/identity diagnostics were removed. This build
retains the original r6 FEX/gameplay behavior, the requested launcher work and
the generic atomic guest-reservation rollback fix. No Kitserver runtime is used.
Normal launch does not write diagnostic logs; Debug launch retains startup and
error logging. Structural archive checks cannot certify every game-data byte.

## Player 1 keyboard

**Settings → Keyboard → Activation delay** offers **Instant** (the new default),
**0.3, 0.6, 1, 1.5 or 2 seconds**. Existing shortcut and position selections are
preserved when loading old preferences; their delay defaults to Instant.
The complete combo must be pressed by **Player 1**. It fires once and rearms only
after release. Player 2 cannot use these combos, navigate or dismiss the OSK.
Player 2 input also cannot hold the OSK's neutral drain open.

**Settings → Keyboard → Shortcut → Capture (Screenshot)** is an additional
opt-in shortcut. A short Capture press from **either controller** requests the
Player 1 keyboard. Keyboard navigation remains with Player 1. Capture uses
the system's short-press notification, independent of the saved combo hold
delay. While this option is active during the game, short Capture presses open
the keyboard instead of taking screenshots. The launcher and other shortcut
choices retain normal screenshot behavior. Existing saved Disabled settings
remain Disabled. No controller identity is available in this system event.

The native controller monitor now opens the overlay when the chord is detected.
Previously it only queued a one-second request for Wine's window event pump.
The focused Wine window thread claims the session before delivering keys;
native workers never call Win32 window/input APIs. Closing an unclaimed overlay
does not wait for Wine. Normal production launch still disables diagnostic
files; Debug launch retains the original startup/error tracing behavior.

The `keyboard-frame` candidate replaces the separate VI keyboard layer with
Autorun-style composition into the game's final Vulkan swapchain image, after
any resolution scaling and before Present. Both shipped renderer choices
(Default DXVK and GPL Async) share this path. The compact keyboard design,
shortcuts, activation delay and Player 1 ownership remain unchanged.

Reference: [Autorun win32u Vulkan OSK at cbb0e4e6](https://github.com/autorunhq/autorun/blob/cbb0e4e6e7fa7f47f328d92441f51bfb507f266f/dlls/win32u/vulkan.c).
This is a narrow adaptation; the original r6 Wine/FEX/Mesa baseline is preserved.
Per-image transfer fences protect staging writes and command-buffer reuse.
The completion semaphore joins the game's existing present wait chain only
when submission succeeds. Moving the keyboard re-records the current image's
copy without rebuilding all buffers or idling the device. A closed keyboard
performs no extra allocation, copy or GPU submit.

Input stays pending until a successful host Present. A failed or absent
presentation (3-second timeout) cancels the invisible keyboard and restores
input after neutral release; no pending keystrokes are delivered. Generation
and session checks reject stale pixels or acknowledgements after close/reopen.
CPU artwork is freed when closed; Vulkan resources are retained for reuse until
swapchain destruction. Debug launch logs requests, first publication, failure
and restoration; production launch remains free of diagnostic file writes.

Host ASan/UBSan tests execute the actual publisher/renderer and Vulkan overlay
with modeled GPU APIs. They cover color conversion, resizing, position, stale
snapshots, acknowledgement, timeouts, semaphore chaining, transfer fences and
failure/partial-allocation cleanup. These checks do not prove Switch visibility.
Test the candidate in PES's name edit field with the selected shortcut, check
navigation/typing/backspace/close, then reopen and move it with Y. The user confirmed the keyboard-frame build working on Switch on 2026-10-12.
The scoped confirmation is recorded in release/v0.4.1-device-confirmation.json;
full compatibility across every configuration remains outside that test.

## Build and validation

Build on the existing devkitPro/WSL setup using a fresh directory:

```sh
python3 tools/build-pes13-39bit.py --work /path/to/new-native-build
python3 tools/build-pes13-39bit-forwarder.py \
  --work /path/to/new-forwarder-build --output /path/to/package \
  --runtime /path/to/new-native-build --approved /path/to/approved-runtime \
  --keys /path/to/local/keys
```

The builder verifies the immutable r6 NRO/ELF and frozen native/FEX source
fingerprints, then records the source delta and final hashes. The forwarder
starts from the hash-pinned, previously tested hbloader and adds only automatic
layout selection and heap bounding. Its actual packed ExeFS, optional marker,
stock-compatible NPDM, CNMT, NACP and canonical target are inspected. Keys are
not included. `tools/build-fextendo-auto-loader.py` rebuilds both stock/HOC loader
variants from the exact distributed source patches in isolation, preserving the
known kernel and official HOC settings. Host tests execute the real descriptor
reader and allocator with modeled filesystem/SVC calls, including malformed and
dual markers, all flag combinations, errors, bounds and cleanup.

ARM64 tests cover the shortcut/display/Wine claim and P2 exclusion, keyboard
delivery, low-window admission, high native allocation and mapping cleanup.
HID, VI, allocator and kernel services are modeled in these tests. Real Switch
launch, OSK and full-match compatibility/performance still require device tests.

Startup tests additionally cover wrong/missing folders, truncated/64-bit EXEs,
links, failed recovery/download/final verification, HIGH gating, the actual UI
renderer, cached verification, per-boot admission, non-dismissible modal,
retry/close/maintenance and single-owner framebuffer lifetime. Repair tests
inject failures and power interruptions at every durable transaction step.
The live host HTTPS test installs and verifies the published catalog; Switch
Wi-Fi/TLS, SD repair and actual boot-patch checks still require device testing.
