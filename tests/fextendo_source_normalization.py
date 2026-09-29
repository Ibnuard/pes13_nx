"""Strictly invert tested runtime edits before historical scope checks."""
import importlib.util
from pathlib import Path
import re


def undo_polling(text, root, filename):
    """Invert only the exact polling edits; keep the historical scope oracle."""
    text, fast_scope = undo_fast_api(text, root, filename)
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
    return normalized, {'applied': True, 'replacements': len(edits), 'roundtrip_exact': True, 'fast_api': fast_scope}


def undo_fast_api(text, root, filename):
    if not any(s in text for s in ('fex_fast_api.h', '[FEX3-FASTAPI]', 'fex_hot_profile.h')):
        return text, {'applied': False}
    root=Path(root)
    spec=importlib.util.spec_from_file_location('fextendo_fast_api_scope',root/'tools/fex_fast_api_patches.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    edits=[]
    def read(name):
        raise AssertionError('Unexpected source read: '+name)
    def replace(name,old,new,count=1):
        if name==filename:
            assert count==1 and old and new and old!=new
            edits.append((old,new))
    module.apply(read,replace,root)
    assert edits
    result=text
    for old,new in reversed(edits):
        assert result.count(new)==1,('Fast API inverse',filename,new)
        result=result.replace(new,old,1)
    replay=result
    for old,new in edits:
        assert replay.count(old)==1,('Fast API replay',filename,old)
        replay=replay.replace(old,new,1)
    assert replay==text
    return result,{'applied':True,'replacements':len(edits),'roundtrip_exact':True}
