"""Use the hash-checked packager for the FPCR guard, control and rollback."""
from pathlib import Path
import json

p = Path(__file__).resolve().parents[1]
checks = json.loads((p / 'local/perf18/round-tests.json').read_text())
assert checks['all_bit_identical'] and checks['cases'] >= 8000
assert (p / 'local/perf18/vendor-before.json').read_bytes() == (p / 'local/perf18/vendor-restored.json').read_bytes()
path = p / 'tools/package-perf17.py'
recipe = path.read_text()
replacements = {
    "work = p / 'local/perf17'": "work = p / 'local/perf18'",
    "b'pes13-nx-0.2.0-perf17-hotblocks'": "b'pes13-nx-0.2.0-perf18-roundguard'",
    "expected_title='PES13-NX PERF17'": "expected_title='PES13-NX PERF18'",
    "control additionally requires PERF17 NRO": "control additionally requires PERF18 NRO",
    "prefix + 'perf17-hotblocks.txt': b'1\\n' if variant == 'hotblocks' else b'0\\n',":
        "prefix + 'perf17-hotblocks.txt': b'0\\n',\n        prefix + 'perf18-roundguard.txt': b'1\\n' if variant == 'hotblocks' else b'0\\n',",
    "'PERF17.md': (p / 'docs/PERF17.md').read_bytes()":
        "'PERF18.md': (p / 'docs/PERF18.md').read_bytes(),\n        'PERF17B-RESULT.md': (p / 'docs/PERF17B-RESULT.md').read_bytes()",
    "files['PERF17-manifest.json']": "files['PERF18-manifest.json']",
    "'variant': variant,": "'variant': 'roundguard' if variant == 'hotblocks' else variant,",
    "'scoped_bigblock': variant == 'hotblocks'": "'scoped_bigblock': False, 'scoped_roundguard': variant == 'hotblocks'",
    "f'pes13-perf17-{variant}.zip'": "('pes13-perf18-' + ('roundguard' if variant == 'hotblocks' else variant) + '.zip')",
}
for old, new in replacements.items():
    assert recipe.count(old) == 1, (old, recipe.count(old))
    recipe = recipe.replace(old, new, 1)
exec(compile(recipe, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
