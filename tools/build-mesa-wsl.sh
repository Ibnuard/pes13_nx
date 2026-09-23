#!/usr/bin/env bash
# Native WSL adaptation of release-108 build-mesa-switch.sh; no Docker.
set -euo pipefail
export DEVKITPRO=${DEVKITPRO:-/opt/devkitpro}
root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
src="$root/mesa-switch"
out="$root/mesa-vulkan"
export CARGO_HOME="$root/toolchains/rust/cargo"
export RUSTUP_HOME="$root/toolchains/rust/rustup"
export PATH="$CARGO_HOME/bin:/usr/lib/llvm-21/bin:/usr/bin:/bin:$DEVKITPRO/devkitA64/bin:$DEVKITPRO/tools/bin"
export MESA_SWITCH_RUST_TARGET=aarch64-unknown-linux-gnu
export MESA_SWITCH_RUSTC="$CARGO_HOME/bin/rustc"
export MESA_SWITCH_BINDGEN=/usr/bin/bindgen
export LIBCLANG_PATH=/usr/lib/llvm-21/lib
expected=b297e230ef88c6c88df2561becf864f979f494a6
test "$(git -C "$src" rev-parse HEAD)" = "$expected"
mkdir -p "$out/tools"
cp "$src/bindgen-switch-wrapper.sh" "$out/tools/bindgen"
cp "$src/rustc-switch-wrapper.sh" "$out/tools/rustc"
cp "$src/bindgen-atomic-shim.h" "$out/tools/bindgen-atomic-shim.h"
chmod +x "$out/tools/bindgen" "$out/tools/rustc"

# Keep host-specific wrapper locations in the build directory, not the source.
python3 - "$src" "$out" <<'PY'
from pathlib import Path
import sys
src, out = map(Path, sys.argv[1:])
t = (src / 'switch_cross_file.txt').read_text()
t = t.replace('/usr/local/libexec/rustc', str(out / 'tools/rustc'))
t = t.replace('/usr/local/libexec/bindgen', str(out / 'tools/bindgen'))
(out / 'switch-wsl.txt').write_text(t)
# Meson 1.10 names its probe sanity.rs. The upstream wrapper already builds
# older Meson sanity probes for the host; extend that same narrow exception.
wrapper = out / 'tools/rustc'
t = wrapper.read_text()
t = t.replace('*sanity_check_for_rust.rs*|*sanitycheckrs.rs*)',
              '*sanity_check_for_rust.rs*|*sanitycheckrs.rs*|*/meson-private/sanity.rs)')
wrapper.write_text(t)
PY

# Compatibility archives requested by the Rust Linux target; implementation
# symbols come from mesa-switch's existing rust_switch_stubs.c.
if [ ! -f "$DEVKITPRO/portlibs/switch/lib/libdl.a" ]; then
    printf '%s\n' 'void __mesa_switch_stub_lib(void) {}' > "$out/empty-posix.c"
    aarch64-none-elf-gcc -c "$out/empty-posix.c" -o "$out/empty-posix.o"
    for name in dl rt util; do
        aarch64-none-elf-ar rcs "$DEVKITPRO/portlibs/switch/lib/lib$name.a" "$out/empty-posix.o"
    done
fi

cd "$src"
if [ ! -f "$out/native/build.ninja" ]; then
    meson setup "$out/native" --buildtype=release \
        -Dvulkan-drivers= -Dgallium-drivers= -Dshader-cache=enabled -Dplatforms= \
        -Dglx=disabled -Degl=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled \
        -Dtools=[] -Dllvm=enabled -Dmesa-clc=enabled -Dprecomp-compiler=enabled -Dinstall-mesa-clc=true
fi
if [ ! -x "$out/native/src/compiler/clc/mesa_clc" ] || [ ! -x "$out/native/src/compiler/spirv/vtn_bindgen2" ]; then
    ninja -C "$out/native" -j"${PES_JOBS:-4}" src/compiler/clc/mesa_clc src/compiler/spirv/vtn_bindgen2
fi
export PATH="$out/native/src/compiler/clc:$out/native/src/compiler/spirv:$PATH"

if [ ! -f "$out/cross/build.ninja" ]; then
    meson setup "$out/cross" --cross-file "$out/switch-wsl.txt" \
        --default-library=static --prefix=/opt/devkitpro/portlibs/switch --libdir=lib \
        --buildtype=release -Doptimization=2 -Db_lto=false -Db_ndebug=true \
        -Dvulkan-drivers=nouveau -Dgallium-drivers=nouveau -Dgallium-rusticl=false \
        -Dplatforms=switch -Degl-native-platform=switch -Dglx=disabled -Degl=enabled \
        -Dopengl=true -Dgles1=enabled -Dgles2=enabled -Dvideo-codecs= \
        -Dshader-cache=enabled -Dxmlconfig=enabled -Dexpat=enabled -Dtools=[] \
        -Dllvm=disabled -Dshared-glapi=disabled -Dshared-llvm=disabled \
        -Dmesa-clc=system -Dprecomp-compiler=system -Dcpp_rtti=false -Dbuild-tests=false \
        -Dnvk-build-id="$expected"
fi
ninja -C "$out/cross" -j"${PES_JOBS:-4}"
meson install -C "$out/cross" --no-rebuild --destdir "$out/install"
lib="$out/install/opt/devkitpro/portlibs/switch/lib"
for archive in "$lib"/*.a; do aarch64-none-elf-ranlib "$archive"; done
inc="$out/install/opt/devkitpro/portlibs/switch/include"
mkdir -p "$inc"
cp -r "$src/include/vulkan" "$src/include/vk_video" "$inc/"
ls -l "$lib/libEGL.a" "$lib/libGL.a" "$lib/libglapi.a" "$lib/libvulkan.a"
git rev-parse HEAD
