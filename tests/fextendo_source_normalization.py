"""Strictly invert independently tested LSFG edits before older scope checks.

No arbitrary preprocessor regions are deleted: the production patch function
supplies every exact before/after pair. Each inverse must match once at the
original indentation, and replaying all production substitutions must restore
the complete input byte for byte. Callers still compare the resulting source
to their historical baseline and bind the unmodified source to the final ELF.
"""
import importlib.util
from pathlib import Path
import re


def undo_lsfg_vulkan(text, root):
    root = Path(root)
    if '#ifdef WINE_NX_LSFG' not in text:
        return text, {'applied': False, 'replacements': 0}
    path = root/'tools/fextendo_lsfg_patches.py'
    spec = importlib.util.spec_from_file_location('fextendo_lsfg_patch_scope', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    edits = []

    def read(name):
        raise AssertionError('LSFG patch now reads source; update strict scope adapter: '+name)

    def replace(name, old, new, count=1):
        if name == 'dlls/win32u/vulkan.c':
            assert count == 1 and old and new and old != new
            edits.append((old, new))

    module.apply(read, replace, root)
    assert edits
    normalized = text
    for old, new in reversed(edits):
        # Acquire admission uses eight-space indents while the original
        # present lock uses four. Anchor to line start so renaming the one
        # original lock cannot accidentally rename the added acquire locks.
        pattern = re.compile('^'+re.escape(new), re.MULTILINE)
        matches = list(pattern.finditer(normalized))
        assert len(matches) == 1, ('LSFG inverse must match exactly once', new, len(matches))
        normalized = pattern.sub(lambda match: old, normalized, count=1)
    assert 'WINE_NX_LSFG' not in normalized
    replay = normalized
    for old, new in edits:
        assert replay.count(old) == 1, ('LSFG replay must match exactly once', old)
        replay = replay.replace(old, new, 1)
    assert replay == text, 'LSFG normalization/replay changed unrelated source'
    return normalized, {'applied': True, 'replacements': len(edits),
                        'roundtrip_exact': True}


def undo_polling(text, root, filename):
    """Invert only the exact polling edits; keep the historical scope oracle."""
    root = Path(root)
    if 'fex_polling_yield.h' not in text and 'fex_polling_counters.h' not in text and '[FEX3-POLL]' not in text:
        return text, {'applied': False, 'replacements': 0}
    spec = importlib.util.spec_from_file_location('fextendo_polling_scope', root/'tools/fex_polling_patches.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    edits = []
    def replace(name, old, new, count=1):
        if name == filename:
            assert count == 1 and old and new and old != new
            edits.append((old, new))
    def read(name):
        raise AssertionError('Unexpected source read: '+name)
    module.apply(read, replace, root)
    assert edits
    normalized = text
    for old, new in reversed(edits):
        assert normalized.count(new) == 1, ('Polling inverse must match once', new)
        normalized = normalized.replace(new, old, 1)
    replay = normalized
    for old, new in edits:
        assert replay.count(old) == 1, ('Polling replay must match once', old)
        replay = replay.replace(old, new, 1)
    assert replay == text
    return normalized, {'applied': True, 'replacements': len(edits), 'roundtrip_exact': True}
