"""WSL diagnostic build: PERF27 behavior, fault table capture and CPU sampling."""
from pathlib import Path
import hashlib, json, os, subprocess, sys
p = Path(__file__).resolve().parents[1]
w = p/'local/perf28'; w.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, str(p/'tests/perf28_fault.py')], check=True)
tests = json.loads((p/'local/perf27/wait-tests.json').read_text())
for name, digest in tests['source_sha256'].items():
    assert hashlib.sha256((p/name).read_bytes()).hexdigest() == digest, name
(w/'wait-tests.json').write_text(json.dumps(tests, indent=2)+'\n')
path = p/'tools/build-perf27.py'; text = path.read_text()
text = text.replace('local/perf27', 'local/perf28').replace('runtime-perf27-wakes', 'runtime-perf28-diagnostics')
text = text.replace('pes13-nx-0.2.0-perf27-wakes', 'pes13-nx-0.2.0-perf28-diagnostics').replace('PES13-NX PERF27', 'PES13-NX PERF28')
text = text.replace('import perf27_patches as perf23_patches', 'import perf28_patches as perf23_patches')
text = text.replace("subprocess.run([sys.executable,str(p/'tests/perf27_wait.py')],check=True)", '')
exec(compile(text, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
report = json.loads((w/'verification.json').read_text())
report.update({'main_cpu_sampling': True, 'diagnostic_only': True, 'startup_fix_claimed': False,
               'hardware_tested': False})
(w/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
print('PERF28 diagnostics built. No new FPS improvement or boot fix claimed.', flush=True)
