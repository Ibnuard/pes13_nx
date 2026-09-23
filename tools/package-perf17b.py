"""Reuse the checked PERF17 packager with isolated identity-fix outputs."""
from pathlib import Path

p = Path(__file__).resolve().parents[1]
path = p / 'tools/package-perf17.py'
recipe = path.read_text()
replacements = {
    "work = p / 'local/perf17'": "work = p / 'local/perf17b'",
    "b'pes13-nx-0.2.0-perf17-hotblocks'": "b'pes13-nx-0.2.0-perf17b-image-identity'",
    "expected_title='PES13-NX PERF17'": "expected_title='PES13-NX PERF17B'",
    "control additionally requires PERF17 NRO": "control additionally requires PERF17B NRO",
    "'PERF17.md': (p / 'docs/PERF17.md').read_bytes()": "'PERF17B.md': (p / 'docs/PERF17B.md').read_bytes()",
    "files['PERF17-manifest.json']": "files['PERF17B-manifest.json']",
    "f'pes13-perf17-{variant}.zip'": "f'pes13-perf17b-{variant}.zip'",
}
for old, new in replacements.items():
    assert recipe.count(old) == 1, old
    recipe = recipe.replace(old, new, 1)
exec(compile(recipe, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
