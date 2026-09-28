# Pinned Switch Mesa from macOS arm64

This builds **Switch AArch64 ELF archives**, not macOS graphics libraries. Mesa
source stays at `b297e230ef88c6c88df2561becf864f979f494a6` (26.2.2), with NVK
and Nouveau configured exactly as `tools/build-mesa-wsl.sh`. No Mesa source
patches, global SDK upgrades, or global portlib replacements are needed.

## Resume prepared build

Run from project root:

```sh
export TMPDIR="$HOME/.hermes/cache/scratch"
python3 tools/build-mesa-macos.py --root "$HOME/.cache/pes13-nx-macos" --jobs 2
```

Individual stages: `prepare`, `native`, `cross`, `install`, `verify`.
`--plan` prints exact configure/build/install commands without changing files.
`cross` builds only; `install` stages libraries and runs verification.
Logs append under `$root/mesa-vulkan/<stage>.log`. An interrupted Ninja build
resumes; do not delete downloaded tools or rebuild from a fresh cache.
Do not run multiple build stages concurrently on the 8 GiB host.

Outputs:

- `$root/mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib`
- `$root/mesa-vulkan/install/opt/devkitpro/portlibs/switch/include`
- `$root/mesa-vulkan/manifest.json`: pin, archive member counts and SHA-256,
  Khronos header hashes, smoke-link command and output hashes.
- `$root/mesa-vulkan/link-smoke.elf` and `link-smoke.nro`: real target link of
  Vulkan, EGL and GL entry points; **not** a gameplay or GPU execution test.

Pass the staged `lib` path to Wine's `WINE_NX_MESA_SWITCH_DIR`. Expected consumer
archives: `EGL`, `GL`, `glapi`, `vulkan`, `mesa_util_c11`, `blake3`, `mesa_util`,
`mesa_util_simd`, `xmlconfig`. Existing `/opt/devkitpro/portlibs/switch/lib`
provides `expat`, `zstd`, and `z`; no isolated replacements were required.
`prepare` stages pinned `vulkan/` and `vk_video/` headers before the long build.

## Prepared host dependencies

All paths below are relative to `$root` unless absolute. Preserve this cache.

| Tool | Version / pin | Location |
| --- | --- | --- |
| Mesa | `b297e230ef88c6c88df2561becf864f979f494a6` | `mesa-switch` |
| LLVM | 21.1.8, Homebrew arm64_sequoia bottle | `toolchains/mesa-llvm/llvm@21/21.1.8` |
| SPIRV-Tools | 1.4.357.0 bottle; pkg-config 2026.3.1 | `toolchains/mesa-spirv-tools/spirv-tools/1.4.357.0` |
| LLVM/SPIR-V translator | `acb023b63a4bafd53d0ba6a1a452b1f0e5671458` (v21.1.0) | `toolchains/mesa-spirv-translator` |
| SPIRV-Headers | `9e3836d7d6023843a72ecd3fbf3f09b1b6747a9e` | `toolchains/mesa-spirv-headers` |
| Rust | 1.93.1 + `aarch64-unknown-linux-gnu` std + rustfmt | `toolchains/mesa-rust/rustup` |
| bindgen-cli | 0.72.1 | `toolchains/mesa-rust/cargo/bin/bindgen` |
| cbindgen | 0.29.4, Homebrew arm64_sequoia bottle | `toolchains/mesa-cbindgen/cbindgen/0.29.4/bin` |
| Meson | 1.10.1, Mako, packaging, ply, PyYAML | `toolchains/mesa-python` venv |
| Host C/C++/ObjC | Apple Clang 16 | `/usr/bin/clang`, `/usr/bin/clang++` |
| Cross C/C++ | devkitA64 GCC 15.2.0 | `/opt/devkitpro/devkitA64` |
| Bison | 3.8.2 | `/opt/homebrew/opt/bison/bin` |
| Ninja / CMake | 1.12.1 / 3.31.6 | `/opt/homebrew/bin` |

Bottle SHA-256 (archives retained next to extracted prefixes):

```text
llvm-21.tar.gz
71f4ead77d52d42da9dd7f34441b45304474837b7ace887c7669048f830df6e6
spirv-tools.tar.gz
b7b146efc7de27c2f4bae1abe2c8f010502345f7012d2850f1259a71a380789c
cbindgen.tar.gz
5048be0ae465821094e3eb1d8e56761e7b590e8f329ecbdafb9f2e1cbe8d1325
```

Initial tool installation used isolated `CARGO_HOME`/`RUSTUP_HOME`, never global
Rust replacement. These commands can resume an interrupted Rust installation:

```sh
export CARGO_HOME="$HOME/.cache/pes13-nx-macos/toolchains/mesa-rust/cargo"
export RUSTUP_HOME="$HOME/.cache/pes13-nx-macos/toolchains/mesa-rust/rustup"
"$HOME/.cargo/bin/rustup" toolchain install 1.93.1 --profile minimal \
  --component rustfmt --target aarch64-unknown-linux-gnu --no-self-update
"$HOME/.cargo/bin/cargo" install bindgen-cli --version 0.72.1 --locked --jobs 2
```

The script deliberately does not silently download or replace missing tools.
For a fresh host, provision these exact tools first; `--plan` documents the
translator and Mesa build commands. Public artifact research is retained in
`mesa-vulkan/artifact-evidence.json`; no matching pinned prebuilt SDK was used.

## macOS-specific safeguards

- Unrelocated Homebrew bottles contain `@@HOMEBREW_PREFIX@@` and
  `@@HOMEBREW_CELLAR@@`. The script fixes extracted Mach-O install IDs and
  dependencies, then ad-hoc signs changed binaries. LLVM stays isolated;
  existing host `/opt/homebrew/opt/zstd` is read only.
- Explicit Apple C/C++/ObjC compilers avoid Homebrew Clang's missing SDK lookup
  during Meson's Objective-C sanity probe. Inherited compiler/linker flags are
  cleared. Native LLVM remains the library/compiler backend for `mesa_clc`.
- Darwin procedural macros use native Rust. Target Rust uses the upstream
  wrapper with `aarch64-unknown-linux-gnu`. Only Meson's native sanity probe
  receives the extra filename exception; real objects remain ELF AArch64.
- Bindgen uses the pinned Switch atomic shim and devkitA64/libnx headers.
- `mesa-vulkan/tools/ar` uses devkitA64 GNU `ar` for Mesa's MRI archive merge.
  Apple `/usr/bin/ar` does not support `-M`. No source patch is necessary.
- Empty `dl`, `rt`, `util` compatibility archives live only under
  `mesa-vulkan/compat/lib`; real runtime symbols come from pinned
  `rust_switch_stubs.c`, not fabricated platform implementations.
- Verification rejects thin, empty, Mach-O, COFF, and non-AArch64 archives.
  Header comparison checks exact pinned bytes. `elf2nro` verifies target image
  generation; only Switch hardware testing can establish gameplay stability.

Host regression tests:

```sh
TMPDIR="$HOME/.hermes/cache/scratch" python3 tests/mesa_macos_prepare.py
```
