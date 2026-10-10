"""Read-only preparation of a reversible duplicate-FSERV comparison.

Only comments two [kload] entries after requiring all three alias DLLs to
match the inspected input. It does not remove files, maps or face assets.
"""
import hashlib
import re

FSERV_ALIAS_SHA = '5c6defc02cbdf3af2586437b3187d19161df206875afef0d2d43506e3848a1ea'


def sha(data): return hashlib.sha256(data).hexdigest()


def modules(raw):
    section, result = b'', []
    for line in raw.splitlines():
        row = line.strip()
        if row.startswith(b'['): section = row.lower()
        if section == b'[kload]':
            m = re.fullmatch(rb'dll\s*=\s*([\w.]+)\s*', row, re.I)
            if m: result.append(m[1].decode().lower())
    return result


def prepare(game):
    directory = game / 'kitserver13'
    original = (directory / 'config.txt').read_bytes()
    hashes = {n: sha((directory / n).read_bytes()) for n in
              ('config.txt', 'fserv.dll', 'fserv_2.dll', 'fserv_3.dll', 'fserv_4.dll')}
    assert all(hashes[f'fserv_{i}.dll'] == FSERV_ALIAS_SHA for i in (2, 3, 4)), 'Different FSERV inputs'
    assert hashes['fserv.dll'] != FSERV_ALIAS_SHA, 'Review the primary module before changing its aliases'
    before = modules(original)
    assert all(before.count(n) == 1 for n in ('fserv', 'fserv_2', 'fserv_3', 'fserv_4'))
    section, lines, removed = b'', [], []
    for line in original.splitlines(keepends=True):
        row = line.strip()
        if row.startswith(b'['): section = row.lower()
        m = re.fullmatch(rb'dll\s*=\s*(fserv_[34])\s*', row, re.I)
        if section == b'[kload]' and m:
            removed.append(m[1].decode().lower())
            line = b'; LW4 loading control, duplicate disabled: ' + line
        lines.append(line)
    altered = b''.join(lines)
    after = modules(altered)
    assert removed == ['fserv_3', 'fserv_4']
    assert after == [n for n in before if n not in removed]
    # This also checks every asset directory, unrelated option and line ending.
    assert altered.replace(b'; LW4 loading control, duplicate disabled: ', b'') == original
    return original, altered, dict(input_sha256=hashes, modules_before=before,
        modules_after=after, config_after_sha256=sha(altered),
        hardware_tested=False, improvement_verified=False,
        change='Comment fserv_3 and fserv_4 only; keep primary fserv and one identical legacy alias fserv_2.',
        limitation='Distinct mapped copies are confirmed, but their exact contribution to the long on-field wait is not measured.')
