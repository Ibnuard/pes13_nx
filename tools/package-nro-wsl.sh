#!/usr/bin/env bash
# Embed the icon and NACP in the existing linked runtime.
set -euo pipefail
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
export DEVKITPRO=${DEVKITPRO:-/opt/devkitpro}
out="$root/runtime-pes13"
icon="$project/assets/icon.jpg"
test -f "$out/wine-nx-runtime.elf"
test -f "$icon"
"$DEVKITPRO/tools/bin/nacptool" --create "PES13-NX" "PES13-NX / Wine-NX" "0.2.0" "$out/pes13-nx.nacp"
"$DEVKITPRO/tools/bin/elf2nro" "$out/wine-nx-runtime.elf" "$out/pes13-nx.nro" "--nacp=$out/pes13-nx.nacp" "--icon=$icon"
python3 "$project/tools/nro_assets.py" "$out/pes13-nx.nro" --icon "$icon"
