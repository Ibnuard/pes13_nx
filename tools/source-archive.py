"""Collect the corresponding patched sources and build scripts for a release."""
import argparse
import os
import tarfile
from pathlib import Path

project = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build-root', type=Path, default=Path(os.environ.get('PES_BUILD_ROOT', Path.home() / '.cache/pes13-nx')))
p.add_argument('--output', type=Path, default=project / 'dist/pes13-nx-sources.tar.gz')
a = p.parse_args()
a.output.parent.mkdir(parents=True, exist_ok=True)
def clean(info):
    parts = Path(info.name).parts
    if '.git' in parts or '__pycache__' in parts:
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    return info
with tarfile.open(a.output, 'w:gz', compresslevel=6) as archive:
    for name in ('src', 'patches', 'config', 'tools', 'tests', 'docs', 'licenses', 'assets',
                 'README.md', 'LICENSE', 'THIRD_PARTY.md', 'dependencies.json', 'requirements.txt'):
        archive.add(project / name, arcname='pes13-nx/' + name, filter=clean)
    archive.add(a.build_root / 'runtime-pes13-source', arcname='upstream/wine-nx', filter=clean)
    archive.add(a.build_root / 'mesa-switch', arcname='upstream/mesa-switch', filter=clean)
print(a.output)
