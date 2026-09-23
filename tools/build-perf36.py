"""Build PERF34 plus the missing scoped FASTNAN emitter reads."""
from pathlib import Path
import json

p = Path(__file__).resolve().parents[1]
path = p / 'tools/build-perf34.py'
text = path.read_text()
for old, new in [('local/perf34', 'local/perf36'),
                 ('runtime-perf34-config', 'runtime-perf36-scoped-fastnan'),
                 ('pes13-nx-0.2.0-perf34-config', 'pes13-nx-0.2.0-perf36-scoped-fastnan'),
                 ('PES13-NX PERF34 CONFIG', 'PES13-NX PERF36 FASTNAN'),
                 ('import perf34_patches as perf23_patches', 'import perf36_patches as perf23_patches')]:
    text = text.replace(old, new)
anchor = '        source=source.replace("assert \'wine_nx_perf25_completed(block, helper.env)\' in generated",'
extra = '''        source=source.replace("assert path.read_bytes()==(p/'local/perf22/generated'/path.name).read_bytes()",
            "assert path.read_text().replace('BOX64DRENV(dynarec_fastnan)','BOX64ENV(dynarec_fastnan)') == ((p/'local/perf22/generated'/path.name) if (p/'local/perf22/generated'/path.name).exists() else (root/'runtime-perf11-source/wine-nx-probe/vendor/box64/src/dynarec/arm64'/path.name)).read_text()")
'''
assert text.count(anchor) == 1
text = text.replace(anchor, extra + anchor)
exec(compile(text, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
w = p / 'local/perf36'
report = json.loads((w / 'verification.json').read_text())
report.update(base='PERF34 CONFIG', actual_new_change='scoped FASTNAN emitter lookup',
              math_emitters_identical_to_perf22=False, math_emitters_identical_to_perf24=False,
              fastnan_changes=json.loads((w / 'fastnan-changes.json').read_text()),
              target_verified=False, hardware_tested=False)
(w / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
