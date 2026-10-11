"""Give a forwarder an installable CNMT revision, not just a display version.

The pinned hacBrewPack defaults to version zero. Build a private copy with one
explicit metadata change; never modify the shared packer or edit packed NCAs
(their hashes must be produced by the packer).
"""
import hashlib
from pathlib import Path
import shutil
import subprocess


def prepare_packer(source: Path, work: Path, version: int) -> Path:
    if not isinstance(version, int) or not 0 <= version <= 0xffffffff:
        raise ValueError('CNMT revision must be an unsigned 32-bit integer')
    if not version:
        return source / 'hacbrewpack'
    dest = work / 'packer-versioned'
    if dest.exists():
        raise ValueError('Use a fresh versioned packer directory')
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(
        '.git', '*.o', '*.a', 'hacbrewpack', 'hacbrewpack.exe', '*.keys', 'keys.dat'))
    file = dest / 'cnmt.c'
    original = file.read_text()
    anchor = '    // Common values\n'
    if original.count(anchor) != 1:
        raise ValueError('Unexpected pinned CNMT source')
    updated = original.replace(anchor, anchor +
        f'    cnmt_ctx->cnmt_header.title_version = 0x{version:08x}u;\n')
    file.write_text(updated)
    (work / 'packer-cnmt-change.txt').write_text(
        'Only cnmt.c changes from the pinned packer checkout.\n'
        f'CNMT title_version: {version}\n'
        f'original_sha256: {hashlib.sha256(original.encode()).hexdigest()}\n'
        f'updated_sha256: {hashlib.sha256(updated.encode()).hexdigest()}\n')
    with (work / 'packer-build.log').open('w') as log:
        subprocess.run(['make', '-j4'], cwd=dest, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    return dest / 'hacbrewpack'
