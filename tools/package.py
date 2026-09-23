"""Package public runtime files using an allowlist, never a whole local SD tree."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from nro_assets import NRO_RELATIVE, inspect_nro

project = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage', type=Path, default=project / 'dist/sd')
p.add_argument('--output', type=Path, default=project / 'dist/pes13-nx-runtime.zip')
a = p.parse_args()
root = a.stage / 'switch/pes13-nx'
files = {NRO_RELATIVE: a.stage / NRO_RELATIVE}
nro_files = sorted(path.relative_to(a.stage).as_posix() for path in a.stage.rglob('*.nro'))
if nro_files != [NRO_RELATIVE]:
    raise ValueError(f'Expected exactly one NRO in the SD payload, found: {nro_files}')
data = files[NRO_RELATIVE].read_bytes()
if data[16:20] != b'NRO0' or b'pes13-nx-0.2.0-vk1-production' not in data:
    raise ValueError('Refusing to package an old helper NRO or a different runtime')
assets = inspect_nro(data, (project / 'assets/icon.jpg').read_bytes())
# Fixed, reviewed dependency manifest prevents saved state or new game files
# inside these trees from being included accidentally.
for row in json.loads((project / 'config/runtime-files.json').read_text()):
    path = root / row['path']
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != row['sha256']:
        raise ValueError(f"Dependency changed: {row['path']}; review the manifest first")
    files['switch/pes13-nx/' + row['path']] = path
for path in (project / 'config').rglob('*.txt'):
    files['switch/pes13-nx/' + path.relative_to(project / 'config').as_posix()] = path
settings_paths = (
    'drive_c/PES13/settings.dat',
    'drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat',
)
for relative in settings_paths:
    files['switch/pes13-nx/' + relative] = project / 'config' / relative
for name in ('README.md', 'LICENSE', 'THIRD_PARTY.md'):
    files[name] = project / name
for path in (project / 'licenses').rglob('*'):
    if path.is_file():
        files[path.relative_to(project).as_posix()] = path
for name in files:
    if name.lower().endswith('.reg') or ('/PES13/' in name and
       not (name.endswith('.txt') or name == 'switch/pes13-nx/drive_c/PES13/settings.dat')):
        raise ValueError('Private game or registry entry in public package')
a.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(a.output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name, path in sorted(files.items()):
        archive.write(path, name)
with zipfile.ZipFile(a.output) as archive:
    assert archive.testzip() is None
    assert [name for name in archive.namelist() if name.endswith('.nro')] == [NRO_RELATIVE]
report = {'file': a.output.name, 'sha256': hashlib.sha256(a.output.read_bytes()).hexdigest(),
          'bytes': a.output.stat().st_size, 'members': len(files),
          'nro_count': 1, 'assets': assets, 'game_included': False, 'private_registry_included': False}
a.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
