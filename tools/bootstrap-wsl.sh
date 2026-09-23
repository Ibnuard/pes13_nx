#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=${PES_BUILD_ROOT:-$HOME/.cache/pes13-nx}
mkdir -p "$root"
python3 - "$project" "$root" <<'PY'
from pathlib import Path
import json, subprocess, sys, tarfile, tempfile, shutil
project, root = map(Path, sys.argv[1:])
lock = json.loads((project / 'dependencies.json').read_text())
def checkout(name, destination):
    dep = lock[name]
    if not destination.exists():
        destination.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'remote', 'add', 'origin', dep['repository']], check=True)
        subprocess.run(['git', '-C', str(destination), 'fetch', '--depth=1', 'origin', dep['commit']], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '-q', '--detach', 'FETCH_HEAD'], check=True)
    rev = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if rev != dep['commit']:
        raise SystemExit(f'{destination}: unexpected source revision; no reset performed')
    if subprocess.check_output(['git', '-C', str(destination), 'status', '--porcelain', '--untracked-files=no'], text=True).strip():
        raise SystemExit(f'{destination}: tracked source changes; no reset performed')
    return destination
base = checkout('wine_nx', root / 'source')
checkout('mesa_switch', root / 'mesa-switch')
src = root / 'runtime-pes13-source'
if not src.exists():
    src.mkdir()
    with tempfile.TemporaryFile() as archive:
        subprocess.run(['git', '-C', str(base), 'archive', 'HEAD'], stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tar:
            tar.extractall(src, filter='data')
    subprocess.run(['git', 'apply', '--check', str(project / 'patches/wine-nx.patch')], cwd=src, check=True)
    subprocess.run(['git', 'apply', str(project / 'patches/wine-nx.patch')], cwd=src, check=True)
    for original, target in (
        ('pes13_preload.c', 'wine-nx-probe/source/pes13_preload.c'),
        ('pes13_graphics.h', 'wine-nx-probe/source/pes13_graphics.h'),
        ('pes13_controller.h', 'wine-nx-probe/source/pes13_controller.h'),
        ('pes13_controller_ui.h', 'wine-nx-probe/source/pes13_controller_ui.h'),
        ('pes13_registry.h', 'dlls/ntdll/unix/pes13_registry.h')):
        shutil.copyfile(project / 'src/runtime' / original, src / target)
    (src / '.pes13-nx-patch.sha256').write_text(__import__('hashlib').sha256((project / 'patches/wine-nx.patch').read_bytes()).hexdigest())
else:
    # Never reset an existing development tree silently.
    import hashlib
    stamp = src / '.pes13-nx-patch.sha256'
    if not stamp.exists() or stamp.read_text() != hashlib.sha256((project / 'patches/wine-nx.patch').read_bytes()).hexdigest():
        raise SystemExit('Existing runtime source is not stamped for this patch. Use a fresh PES_BUILD_ROOT or inspect it manually.')
checkout('box64', src / 'wine-nx-probe/vendor/box64')
print('Pinned sources ready:', root)
PY
