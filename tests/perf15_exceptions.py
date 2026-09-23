"""Exercise actual patched fault helpers on the host; no ARM64 execution claim."""
from pathlib import Path
import subprocess, sys, tempfile

p = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1])
engine = (root/'wine-nx-probe/source/wow64_box64_engine.c').read_text()
cpu = (root/'dlls/winebox64/cpu.c').read_text()
faults = engine[engine.index('/* The address the last guest access violation'):engine.index('/* Only interpreter objects')]
dispatch = cpu[cpu.index('static BOOL raise_guest_exception('):cpu.index('void WINAPI BTCpuSimulate(')]
fixture = (p/'tests/perf15_exception_fixture.c').read_text()
assert fixture.count('/* ACTUAL_FAULT_HELPERS */') == 1
assert fixture.count('/* ACTUAL_PE_DISPATCH */') == 1
fixture = fixture.replace('/* ACTUAL_FAULT_HELPERS */', faults).replace('/* ACTUAL_PE_DISPATCH */', dispatch)
with tempfile.TemporaryDirectory(prefix='pes13-perf15-') as tmp:
    src = Path(tmp)/'check.c'
    src.write_text(fixture)
    exe = Path(tmp)/'check'
    subprocess.run(['cc', '-std=gnu11', '-fms-extensions', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
        '-D__WINESRC__', '-D_WIN64', '-DWINE_NX_BOX64_DYNAREC', '-fsanitize=undefined',
        '-I'+str(root/'include'), '-I'+str(root/'dlls/winebox64'), str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
