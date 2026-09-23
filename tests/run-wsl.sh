#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
src="$root/runtime-pes13-source"
out="$root/host-tests"
mkdir -p "$out"
gcc -std=c11 -Wall -Wextra -Werror -I"$project/tests/preload-shims" \
    "$project/src/runtime/pes13_preload.c" "$project/tests/preload_guard.c" -o "$out/preload"
for scenario in 1 2 3 4 5 6 7; do "$out/preload" "$scenario"; done
# Extract the real default block so its size and contents are covered.
python3 - "$src" "$out" <<'PY'
from pathlib import Path
import sys
src, out = map(Path, sys.argv[1:])
text = (src / 'wine-nx-probe/source/runtime.c').read_text()
# The strings themselves contain semicolons. End at the declaration terminator.
start = text.index('static const char runtime_environment[]')
end = text.index(';\n', start) + 1
(out / 'pes13_test_environment.h').write_text(text[start:end] + '\n')
PY
gcc -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
    -I"$out" -I"$project/src/runtime" "$project/tests/graphics_environment.c" -o "$out/graphics"
"$out/graphics"
gcc -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
    -I"$src/dlls/ntdll/unix" -I"$project/src/runtime" \
    "$project/tests/install_registry.c" -o "$out/registry"
if [ -f "$project/local/config/pes13-install.reg" ]; then
    "$out/registry" "$project/local/config/pes13-install.reg"
else
    "$out/registry"
fi

gcc -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
    -I"$src/include" -I"$src/dlls/xinput1_3" -I"$project/src/runtime" \
    "$project/tests/controller.c" -o "$out/controller"
"$out/controller"
python3 "$project/tests/settings_profile.py"
