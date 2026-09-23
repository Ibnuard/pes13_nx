"""Validate the actual capture header with real captured instructions and sanitizers."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, tempfile
p = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(p/'tools'))
from perf28_patches import patch_unix
from perf15_patches import apply_hunks
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
original = (root/'runtime-perf11-source/wine-nx-probe/source/wow64_box64_unix.c').read_text()
base = apply_hunks(original, (p/'patches/perf15/wine-nx-probe_source_wow64_box64_unix.c.patch').read_text())
patched = patch_unix(base, p)
assert patched.index('pes28_after_run(status, p)') > patched.index('NTSTATUS status = wine_nx_box64_run')
assert patched.count('pes28_after_run(status, p)') == 1
with tempfile.TemporaryDirectory(prefix='perf28-fault-', dir=root) as tmp:
    exe = Path(tmp)/'fault'
    subprocess.run(['cc','-O2','-g','-std=gnu11','-Wall','-Wextra','-Werror','-pthread',
        '-fsanitize=address,undefined',str(p/'tests/perf28_fault.c'),'-o',str(exe)], check=True)
    subprocess.run([str(exe),str(p/'local/perf28/captures/fail-1/slot-5-x86.bin')], check=True, timeout=30)
w = p/'local/perf28'; w.mkdir(parents=True, exist_ok=True)
report = {'asan_ubsan':'PASS', 'real_capture_signature':'PASS', 'corrupt_range_and_read_failure_tests':'PASS',
          'concurrent_once_only':'PASS', 'guest_context_unchanged':'PASS', 'hook_after_emulator_unwind':True,
          'source_sha256':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [
              p/'src/runtime/pes13_perf28_fault.h',p/'src/runtime/pes13_perf28_unix.h',
              p/'tests/perf28_fault.c',p/'tests/perf28_fault.py',p/'tools/perf28_patches.py']}}
(w/'fault-tests.json').write_text(json.dumps(report, indent=2)+'\n')
