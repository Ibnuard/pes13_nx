"""Build a PERF12-based ARM64 suspend backoff A/B DLL under WSL."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home()/'.cache/pes13-nx')))
source = root/'source/dlls/ntdll/signal_arm64.c'
pe = root/'pe'
dll = pe/'dlls/ntdll/aarch64-windows/ntdll.dll'
obj = pe/'dlls/ntdll/aarch64-windows/signal_arm64.o'
reference = p/'local/perf12/ntdll-server-suspend.dll'
expected = '613a22358e6cdca18bb6bb1fc8522b5d79cf08e485e309997c2533b04ffca855'
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(reference.read_bytes()) == expected, 'PERF12 reference changed'
original = source.read_text()
start = original.index('NTSTATUS WINAPI RtlWow64SuspendThread(')
end = original.index('/*************************************************************************', start)
replacement = (p/'src/runtime/pes13_suspend_backoff.h').read_text() + '\n'
assert replacement.count('NTSTATUS WINAPI RtlWow64SuspendThread(') == 1
dest = p/'local/perf13'
dest.mkdir(parents=True, exist_ok=True)
compiler = root/'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64/bin'
env = dict(os.environ)
env['PATH'] = f'{compiler}:/opt/devkitpro/devkitA64/bin:/opt/devkitpro/tools/bin:/usr/bin:/bin'
subprocess.run(['python3', str(p/'tests/perf13_suspend.py'),
                str(root/'runtime-perf11-source')], env=env, check=True)
with tempfile.TemporaryDirectory(prefix='perf13-pe-', dir=root) as tmp:
    saved = []
    for i, path in enumerate((source, obj, dll)):
        assert path.is_file(), path
        backup = Path(tmp)/str(i)
        shutil.copy2(path, backup)
        saved.append((path, backup))
    try:
        source.write_text(original[:start]+replacement+original[end:])
        subprocess.run(['make', '-C', str(pe), '-j4',
                        'dlls/ntdll/aarch64-windows/ntdll.dll'], env=env, check=True)
        shutil.copy2(dll, dest/'ntdll-suspend-backoff.dll')
        asm = subprocess.check_output([str(compiler/'llvm-objdump'), '-dr', str(obj)], text=True)
        body = asm.split('<RtlWow64SuspendThread>:', 1)[1].split('\n\n', 1)[0]
        (dest/'suspend-disassembly.txt').write_text(body+'\n')
    finally:
        for path, backup in saved:
            shutil.copy2(backup, path)
    for path, backup in saved:
        assert path.read_bytes() == backup.read_bytes(), path
shutil.copy2(reference, dest/'ntdll-perf12-rollback.dll')
(dest/'build.json').write_text(json.dumps({
    'baseline_restored': True, 'rollback_byte_identical_to_perf12': True,
    'wrapper_sha256': sha(replacement.encode()),
    'test_sha256': sha((dest/'ntdll-suspend-backoff.dll').read_bytes()),
    'rollback_sha256': expected,
}, indent=2))
print('PERF13 built; original source, PE object and DLL restored', flush=True)

