# PES13 original: FEXTendo 39-bit branch

Release checkpoint: **v0.4.0**. Launcher display, NRO metadata and the
copy-ready package use version `0.4.0`.

`pes13-39bit-patch` starts from `main` commit
`65f6962` and the approved original production runtime `0.3.8-r6`.
It does not use the Kitserver/patch-release runtime.
The generic Wine commit rollback fix is backported independently: a failed
backing allocation/map retains its original guest reservation and can be retried.
The stock r6 failure was reproduced before applying that fix.

The native ARM64 process requests 39-bit address space. Wine's x86 guest keeps
addresses from `0x00200000` to below 4 GiB. Physical memory remains limited by
the kernel's process allowance; this is not a guarantee of 4 GiB usable RAM.

The forwarder contains the 32-byte ExeFS `fxtmem` descriptor, ABI 1, layout 1,
flags/reserved zero. FEXTendo's matching Loader/Mesosphere pair detects that
descriptor independently of the game Title ID. Installing the NSP alone on
an ordinary boot does not enable the required layout.

## Install the copy-ready overlay

1. Install/boot the compatible **FEXTendo Patch** environment.
2. Copy the package's `switch` folder to the SD root. It contains identical
   `pes13-39bit.nro` and `pes13-fex.nro`, so both HOME tiles get startup checks.
   Back up the existing NRO if you want a rollback. Game files are required.
3. Install `forwarders/PES13-FEXTendo-39bit.nsp`.
4. Start **PES13 FEXTendo 39-bit** from HOME.

The distinct 39-bit HOME title coexists with the existing 32-bit tile.
The launcher supports original 32-bit no-alias for Medium/Low; HIGH is locked.
Ordinary 36-bit/39-bit or alias layouts can show checks and the launcher but
cannot enter Wine. Use a compatible HOME tile instead of Homebrew Menu.
It checks high native code/stack/TLS/backing and low RX/RW mapping support,
including cleanup, before admitting the game. Libnx's native address allocator
excludes the low guest window from its first initialization.

## Automatic startup checks (0.4.0)

Before artwork and Wine load, the built-in startup screen checks the game
location, its PE32 executable and `img/dt00.img`, then verifies 221 immutable
runtime files by size and SHA256. The runtime catalog includes Wine/FEX,
NLS/fonts, bundled renderer sources, launcher artwork and graphics templates.
Missing or changed runtime files are downloaded automatically from the pinned
official `v0.3.8-r9` asset. The complete ZIP and each staged member must match
the checksums compiled into the NRO. Game/Kitserver files, active renderer
copies/configs, saves, registry, preferences and the NRO are not repair targets.
An existing interrupted repair is recovered before checking again.

A healthy installation works offline. Verification is read-only and ends
before gameplay; there is no periodic scan or automatic diagnostic logging.
Repair needs Wi-Fi, a correct system date and approximately 300 MB free on SD.
Failure shows an installation/repair popup and a Retry/Close screen; Wine
cannot start with an incomplete runtime. B or Plus cancels safely. Allow an
installation commit to finish before powering off.

The boot status comes from the running process's kernel layout and low RX/RW
mapping probes, not the presence of patch files on SD. HIGH is unavailable
unless the 39-bit low-window preflight passes. A saved HIGH selection falls
back to Medium with an explanation; selecting HIGH and launching it are both
guarded. The startup console releases its framebuffer and restores the silent
stdout device before the GUI/game takes over.

## Player 1 keyboard

The launcher shortcut choice remains configurable. With **L + R + Plus**, hold
all three buttons on **Player 1** for 0.6 seconds. Player 2 cannot request,
navigate or dismiss the OSK. Player 2 input also cannot hold the OSK's neutral
drain open.

The native controller monitor now opens the overlay when the chord is detected.
Previously it only queued a one-second request for Wine's window event pump.
The focused Wine window thread claims the session before delivering keys;
native workers never call Win32 window/input APIs. Closing an unclaimed overlay
does not wait for Wine. Normal production launch still disables diagnostic
files; Debug launch retains the original startup/error tracing behavior.

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
uses the exact high-native hbloader previously exercised by the device probe;
its packed ExeFS/NPDM/target are inspected after packaging. Keys are not included.

ARM64 tests cover the shortcut/display/Wine claim and P2 exclusion, keyboard
delivery, low-window admission, high native allocation and mapping cleanup.
HID, VI, allocator and kernel services are modeled in these tests. Real Switch
launch, OSK and full-match compatibility/performance still require device tests.

Startup tests additionally cover wrong/missing folders, truncated/64-bit EXEs,
links, failed recovery/download/final verification, HIGH gating, the actual UI
renderer, console ownership and restoration of silent stdout. Repair tests
inject failures and power interruptions at every durable transaction step.
The live host HTTPS test installs and verifies the published catalog; Switch
Wi-Fi/TLS, SD repair and actual boot-patch checks still require device testing.
