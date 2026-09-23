# Building in WSL

Use a Linux filesystem for the build cache (not `/mnt/c` or `/mnt/d`). The
project itself may remain on a Windows drive. Scripts default to
`PES_BUILD_ROOT=$HOME/.cache/pes13-nx`; export another absolute path if desired.
Set `PES_JOBS` to change the default four build jobs.

The tested environment used Ubuntu 26.04, devkitA64 GCC 16.1.0, libnx 4.12.0,
LLVM 21, Rust 1.93.1 and Meson 1.10.1. Install devkitPro/devkitA64 and Switch
portlibs first. The native runtime requires SDL2, SDL2_ttf, FreeType, HarfBuzz,
PNG, zlib, bzip2, libdrm_nouveau, libexpat and libzstd. Keep a record of package
versions when changing the SDK; a newer SDK has not been hardware validated here.

Additional host packages used for the Mesa build:

```sh
sudo apt install git cmake ninja-build build-essential bison flex python3-pip \
  meson python3-mako python3-packaging python3-ply pkg-config \
  clang-21 llvm-21-dev libclang-21-dev libclang-cpp21-dev \
  libllvmspirvlib-21-dev libclc-21-dev spirv-tools spirv-tools-dev \
  bindgen cbindgen libzstd-dev libexpat1-dev libz-dev libunwind-dev
```

The additional devkitPro packages are named `switch-libzstd` and
`switch-libexpat`. Install the LLVM-MinGW toolchain listed in
`dependencies.json` into
`$PES_BUILD_ROOT/toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64`.
Install Rust 1.93.1 with `rustfmt` and `aarch64-unknown-linux-gnu` using
`CARGO_HOME=$PES_BUILD_ROOT/toolchains/rust/cargo` and
`RUSTUP_HOME=$PES_BUILD_ROOT/toolchains/rust/rustup`.

From this repository in WSL:

```sh
export PES_BUILD_ROOT="$HOME/.cache/pes13-nx"
bash tools/bootstrap-wsl.sh
bash tools/build-pe-wsl.sh
bash tools/build-mesa-wsl.sh
bash tools/build-runtime-wsl.sh
python3 tools/verify-runtime.py --build-root "$PES_BUILD_ROOT"
```

Bootstrap fetches exact Wine-NX, Mesa Switch and Box64 revisions and applies
`patches/wine-nx.patch` plus `src/runtime/`. It refuses to reset existing source
changes. After changing a patch, use a fresh build cache or update the source
manually and review it. Mesa's build creates host shader compiler tools, then
static nvc0/EGL/OpenGL and NVK/Vulkan libraries in a staged SDK. The small Rust
wrapper adjustment is for Meson 1.10's host sanity probe.

The first Mesa build is substantial. Subsequent runtime builds reuse it. Output:

```text
$PES_BUILD_ROOT/runtime-pes13/pes13-nx.nro
```

This NRO contains the runtime and starts `C:\PES13\pes2013.exe` automatically.
There is no helper NRO or next-load step. Generated ELF files and any older
build outputs in the cache are not part of the SD package.

`build-runtime-wsl.sh` calls `package-nro-wsl.sh` to embed `assets/icon.jpg`
and the NACP metadata. The icon is a 256x256 baseline JPEG. Sphaira requires a
nonempty icon to install a forwarder, so `nro_assets.py` checks it immediately
after packaging and again when staging and building the release ZIP.
For metadata-only changes, run `bash tools/package-nro-wsl.sh` to reuse the
existing ELF. Package 0.2.0 uses the `pes13-nx-0.2.0-vk1-production` runtime
marker and NACP version 0.2.0. Its controller helpers are copied from `src/runtime/`
during bootstrap; after editing them, synchronize the development source tree
before building, just as for the other runtime helpers.

## Assemble and verify

Download the `test-build-2` dependency ZIP from the pinned
[Wine-NX release](https://github.com/danfromtico/wine-nx/releases/tag/test-build-2).
`tools/stage.py` verifies its SHA256 and copies only Windows modules, fonts,
NLS and DXVK. It does not use the release's original runtime NRO.

```sh
python3 -m venv .cache/venv
. .cache/venv/bin/activate
pip install -r requirements.txt
python tools/stage.py --release /path/to/wine-test-build-2.zip \
  --extra-dlls "$PES_BUILD_ROOT/extra-dlls" \
  --build "$PES_BUILD_ROOT/runtime-pes13" \
  --game /path/to/your/PES13 --metadata local/config/pes13-install.reg
python tools/check_payload.py dist/sd/switch/pes13-nx \
  --dxvk --entry pes2013.exe --entry rld.dll \
  --entry vulkan-1.dll --entry winevulkan.dll --output local/payload-check.json
python tools/package.py
```

Omit `--game` and `--metadata` to stage runtime dependencies alone; the
game import check requires your game. `stage.py` refuses to overwrite an
existing output. The checked-in dependency manifest pins the current package;
if rebuilding PE DLLs changes their bytes, review the changes and update the
manifest before making a new release. Do not silently accept changed inputs.

`tests/run-wsl.sh` checks early address reservations, registry preservation and
UTF-16/environment boundaries, controller face buttons/chords, XInput ABI,
input handover and trace limits. `verify-runtime.py` checks the linked VA hook,
Vulkan/WoW64 bridge, SD paths, automatic PES startup and build identity. The
package check requires exactly one NRO at `switch/pes13-nx/pes13-nx.nro`, with
valid embedded icon and NACP sections. The import audit includes
delay imports, forwarded exports and the actual API-set schema. These are
local checks; they cannot establish frame rate or complete game compatibility.

The isolated startup experiment in [PERF15.md](PERF15.md) builds the exception
backport on the PERF11/Box64 0.4.4 source tree plus PERF14 mapping guards.
Its NRO and ARM64 winebox64.dll use ABI 4 and must be installed or rolled back
together. Use `tools/build-perf15.py` under WSL and `tools/package-perf15.py`
to produce the test and rollback archives; these are overlays for an existing
PERF13/PERF14 installation, not replacements for the base staging procedure.

[PERF16.md](PERF16.md) documents configuration/D3D9 overlays for sampling
and renderer comparison on that stable PERF15 pair. Build them with
`python tools/package-perf16.py`; they do not rebuild the NRO or replace
the native CPU backend. The corresponding log analysis is recorded in
[PERF15-RESULT.md](PERF15-RESULT.md).

## Publishing

The current performance experiment is documented in [PERF25.md](PERF25.md),
with the preceding hardware measurements in [PERF24-RESULT.md](PERF24-RESULT.md).
Its WSL build and verifier retain the prepared PERF11 source tree and produce
an isolated PERF25 NRO. The main overlay keeps SAFEFLAGS=2 and X87DOUBLE=1,
disables CPU sampling and includes a matched pair-copy control plus PERF24
rollback. These remain hardware test overlays, not a confirmed 30 FPS release.

Publish this source repository and the runtime-only ZIP, never the local game
tree, registry metadata or local backups. Keep the pinned source revisions,
patch and build scripts with each release. When distributing runtime binaries,
provide the corresponding modified Wine source as well; the source archive
tool includes the patched source, Box64 and Mesa alongside this project's
build scripts. Third-party notices belong with the binary package.

`tools/make-settings.py` reconstructs PES's 852-byte settings profile from the
user's supported `settings.exe`, applies the tested PC flags and recomputes the
native CRC16. The active profile at
`config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat`
is validated by `tests/settings_profile.py` and packaged as runtime
configuration. It contains no game executable, installation code or save data.
