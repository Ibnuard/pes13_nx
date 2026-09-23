#!/usr/bin/env bash
# Build the matched Wine PE modules and the XInput forwarding shim.
set -euo pipefail
build_root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
toolchain="$build_root/toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64"
export PATH="$toolchain/bin:/usr/bin:/bin"
src="$build_root/source"
pe="$build_root/pe"
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$pe" "$build_root/extra-dlls"
test -x "$toolchain/bin/i686-w64-mingw32-clang"
if [ ! -f "$pe/Makefile" ]; then
    (cd "$pe"; "$src/configure" -C --enable-archs=aarch64,i386 --enable-winebox64=aarch64 --without-x --without-freetype)
fi
modules=("$@")
if [ ${#modules[@]} -eq 0 ]; then
    mapfile -t modules < <(python3 - "$project/config/extra-dlls.json" <<'PYDLL'
import json, sys
print('\n'.join(v['file'] for v in json.load(open(sys.argv[1])) if v['file'] != 'xinput1_1.dll'))
PYDLL
    )
fi
targets=()
for module in "${modules[@]}"; do
    [[ "$module" =~ ^[a-zA-Z0-9_.-]+\.(dll|drv|acm)$ ]] || exit 2
    folder=${module%.dll}
    # Wine uses directories named winspool.drv and msacm32.drv for driver DLLs.
    targets+=("dlls/$folder/i386-windows/$module")
done
# Native audio sources also include these generated COM headers; the selected
# PE DLLs alone need not request them on a fresh build tree.
make -C "$pe" -j"${PES_JOBS:-4}" include/audioclient.h include/mmdeviceapi.h include/audiopolicy.h "${targets[@]}"
for module in "${modules[@]}"; do
    folder=${module%.dll}
    cp "$pe/dlls/$folder/i386-windows/$module" "$build_root/extra-dlls/"
done
# PE forwarders plus a trivial DllMain; no replacement controller semantics.
if [ ! -f "$build_root/extra-dlls/xinput1_1.dll" ] || \
   [ "$project/src/shims/xinput1_1.c" -nt "$build_root/extra-dlls/xinput1_1.dll" ] || \
   [ "$project/src/shims/xinput1_1.def" -nt "$build_root/extra-dlls/xinput1_1.dll" ]; then
    "$toolchain/bin/i686-w64-mingw32-clang" -shared -nostdlib -Wl,--entry,_DllMain@12 \
        "$project/src/shims/xinput1_1.c" "$project/src/shims/xinput1_1.def" \
        -o "$build_root/extra-dlls/xinput1_1.dll"
fi
echo "Additional DLLs: $build_root/extra-dlls"
