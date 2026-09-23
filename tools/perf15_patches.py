"""Apply the checked, narrow Wine-NX exception backport without fuzzy matches."""
from pathlib import Path


def apply_hunks(text, patch):
    hunks = []
    old, new = [], []
    for line in patch.splitlines(keepends=True):
        if line.startswith('@@ '):
            if old or new:
                hunks.append((''.join(old), ''.join(new)))
            old, new = [], []
        elif line.startswith(('--- ', '+++ ')):
            continue
        elif line.startswith(' '):
            old.append(line[1:]); new.append(line[1:])
        elif line.startswith('-'):
            old.append(line[1:])
        elif line.startswith('+'):
            new.append(line[1:])
    if old or new:
        hunks.append((''.join(old), ''.join(new)))
    assert hunks, 'Empty patch'
    for old, new in hunks:
        assert old and text.count(old) == 1, f'Patch context ambiguous or missing: {old[:180]!r}'
        text = text.replace(old, new, 1)
    return text


def source_changes(root, patch_dir):
    result = {}
    for patch in sorted(Path(patch_dir).glob('*.patch')):
        content = patch.read_text()
        header = content.splitlines()[0]
        assert header.startswith('--- a/')
        relative = Path(header[6:])
        assert not relative.is_absolute() and '..' not in relative.parts
        target = root / relative
        result[target] = apply_hunks(target.read_text(), content)
    return result
