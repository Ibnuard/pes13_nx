"""Assemble a PES-only SD tree from verified runtime inputs; game is optional."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--release', type=Path, required=True, help='Wine-NX test-build-2 ZIP (dependencies only)')
p.add_argument('--extra-dlls', type=Path, required=True)
p.add_argument('--build', type=Path, required=True)
p.add_argument('--game', type=Path, help='Your installed PES2013 directory')
p.add_argument('--metadata', type=Path, help='Your exported pes13-install.reg')
p.add_argument('--output', type=Path, default=project / 'dist/sd')
a = p.parse_args()
sha = lambda path: hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
lock = json.loads((project / 'dependencies.json').read_text())
if a.output.exists():
    p.error('Output exists; choose a fresh directory. Nothing was removed.')
if sha(a.release) != lock['wine_nx']['release_archive_sha256']:
    p.error('Unexpected dependency archive SHA256')
data = (a.build / 'pes13-nx.nro').read_bytes()
if data[16:20] != b'NRO0' or b'pes13-nx-0.2.0-vk1-production' not in data:
    p.error('pes13-nx.nro: not the self-starting PES13-NX runtime')
if b'sdmc:/switch/wine/' in data:
    p.error('pes13-nx.nro: stale SD path')
inspect_nro(data, (project / 'assets/icon.jpg').read_bytes())
if a.game and not (a.game / 'pes2013.exe').is_file():
    p.error('Game directory must contain pes2013.exe')
root = a.output / 'switch/pes13-nx'
root.mkdir(parents=True)
with zipfile.ZipFile(a.release) as archive:
    for member in archive.infolist():
        if member.is_dir() or not member.filename.startswith('switch/wine/'):
            continue
        relative = PurePosixPath(member.filename).relative_to('switch/wine')
        if '..' in relative.parts or relative.is_absolute():
            raise ValueError('Unsafe archive path')
        # Retain Windows modules/fonts, NLS and DXVK. No demos or stock NRO.
        name = relative.as_posix()
        if not (name.startswith(('drive_c/windows/', 'share/')) or name == 'drive_c/dxvk/d3d9.dll'):
            continue
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.read(member))
for row in json.loads((project / 'config/extra-dlls.json').read_text()):
    source = a.extra_dlls / row['file']
    # Rebuilt PE timestamps may differ; validate architecture/imports afterwards.
    if not source.is_file():
        raise FileNotFoundError(source)
    shutil.copy2(source, root / 'drive_c/windows/syswow64' / source.name)
if sha(root / 'drive_c/dxvk/d3d9.dll') != lock['dxvk']['d3d9_sha256']:
    raise ValueError('Unexpected DXVK DLL')
shutil.copy2(a.build / 'pes13-nx.nro', root / 'pes13-nx.nro')
game = root / 'drive_c/PES13'
game.mkdir(parents=True, exist_ok=True)
if a.game:
    # Install files only. Never copy unpacked diagnostics or old renderer overrides.
    for name in ('pes2013.exe', 'settings.exe', 'rld.dll'):
        if (a.game / name).is_file():
            shutil.copy2(a.game / name, game / name)
    if (a.game / 'img').is_dir():
        shutil.copytree(a.game / 'img', game / 'img')
for item in (project / 'config').rglob('*.txt'):
    relative = item.relative_to(project / 'config')
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(item, root / relative)
for relative in (
    'drive_c/PES13/settings.dat',
    'drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat',
):
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project / 'config' / relative, destination)
if a.metadata:
    shutil.copy2(a.metadata, root / 'pes13-install.reg')
print('SD payload:', a.output.resolve())
print('Game included:', bool(a.game), '| Private metadata included:', bool(a.metadata))
