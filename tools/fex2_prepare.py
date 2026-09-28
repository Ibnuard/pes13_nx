"""Create isolated Wine source snapshots; never patch the Box64 build tree."""
from pathlib import Path
import hashlib
import json
import shutil
import os


def prepare(root, project, version='wine2'):
    if version not in ('wine2', 'wine3'):
        raise ValueError('Unsupported FEX Wine snapshot')
    work = root / 'fex-experiment' / version
    work.mkdir(parents=True, exist_ok=True)
    for kind, origin in (('native-source', root / 'runtime-perf11-source'),
                         ('pe-source', root / 'source')):
        dest = work / kind
        stamp = work / (kind + '.json')
        if dest.exists():
            if not stamp.exists():
                raise RuntimeError(f'Incomplete snapshot: {dest}; inspect before reusing')
            continue
        print(f'Snapshot {origin} -> {dest}', flush=True)
        shutil.copytree(origin, dest, symlinks=True,
                        ignore=shutil.ignore_patterns('.git', '__pycache__'))
        hashes = {str(p.relative_to(dest)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in dest.rglob('*') if p.is_file() and not p.is_symlink()}
        stamp.write_text(json.dumps({'origin': str(origin), 'files': hashes}, indent=2) + '\n')
    print('Isolated snapshots ready', flush=True)
    return work


if __name__ == '__main__':
    prepare(Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build')),
            Path(__file__).resolve().parents[1])
