#!/usr/bin/env bash
# Build one self-starting PES13 NRO. No container is used.
set -euo pipefail
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
export DEVKITPRO=${DEVKITPRO:-/opt/devkitpro}
export DEVKITA64="$DEVKITPRO/devkitA64"
export PATH="$DEVKITA64/bin:$DEVKITPRO/tools/bin:/usr/bin:/bin"
src="$root/runtime-pes13-source"
out="$root/runtime-pes13"
mesa="$root/mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib"
test -f "$mesa/libvulkan.a"
test -f "$src/wine-nx-probe/source/pes13_preload.c"
test -f "$root/pe/include/config.h"
mkdir -p "$out" "$project/local/reports"
bash "$project/tests/run-wsl.sh"
if [ ! -f "$out/build.ninja" ]; then
    cmake -S "$src/wine-nx-probe" -B "$out" -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE="$src/wine-nx-probe/cmake/switch-devkitA64.cmake" \
        -DWINE_NX_PE_BUILD_DIR="$root/pe" -DWINE_NX_BOX64_DYNAREC=ON \
        -DWINE_NX_STOCK_MESA=OFF -DWINE_NX_MESA_SWITCH_DIR="$mesa" \
        -DCMAKE_BUILD_TYPE=Release
fi
cmake --build "$out" --target wine-nx-runtime -j"${PES_JOBS:-4}"
bash "$project/tools/package-nro-wsl.sh"
printf 'Built single NRO: %s/pes13-nx.nro\n' "$out"
