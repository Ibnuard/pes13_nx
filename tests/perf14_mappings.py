"""Inject native allocation probes between real Horizon mapping operations.

Uses the real three transition functions; kernel/libnx primitives are a host
model. Detects windows in the old code, then tests the patched code and errors.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

p = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(p/'tools'))
from perf14_mappings import patch_horizon

def function(text, name):
    start = text.index(name+'(')
    start = text.rfind('\n', 0, start)+1
    brace = text.index('{', start)
    level = 1
    end = brace+1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]+'\n'

original = Path(sys.argv[1]).read_text()
fixture = (p/'tests/perf14_mapping_fixture.c').read_text()
for patched, source in ((False, original), (True, patch_horizon(original))):
    bodies = '\n'.join(function(source, name) for name in
        ('change_section_range', 'protect_range_locked', 'horizon_mmap_section'))
    text = fixture.replace('/* REAL_TRANSITIONS */', bodies)
    with tempfile.TemporaryDirectory(prefix='pes13-mapping-test-') as tmp:
        c, binary = Path(tmp)/'mapping.c', Path(tmp)/'mapping'
        c.write_text(text)
        subprocess.run(['cc', '-O2', '-pthread', f'-DPATCHED={int(patched)}', str(c), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
