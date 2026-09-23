"""Build an ARM64 ntdll test forwarding WoW64 suspend to Horizon's server.

No NRO or Box64 setting changes. Run in WSL with PES_BUILD_ROOT set.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import ast

p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT',str(Path.home()/'.cache/pes13-nx')))
source=root/'source/dlls/ntdll/signal_arm64.c'
pe=root/'pe'
dll=pe/'dlls/ntdll/aarch64-windows/ntdll.dll'
obj=pe/'dlls/ntdll/aarch64-windows/signal_arm64.o'
original=source.read_text()
start=original.index('NTSTATUS WINAPI RtlWow64SuspendThread(')
end=original.index('/*************************************************************************',start)
replacement='''NTSTATUS WINAPI RtlWow64SuspendThread( HANDLE thread, ULONG *count )
{
    /* PERF12: Horizon owns the supported start-gate semantics. Running-thread
     * suspension is explicitly refused there; propagate its actual status
     * instead of claiming success with no thread-state change. */
    return NtSuspendThread( thread, count );
}

'''
dest=p/'local/perf12'
dest.mkdir(parents=True,exist_ok=True)
(dest/'suspend-wrapper.c.txt').write_text(replacement)
env=dict(os.environ)
compiler=root/'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64/bin'
env['PATH']=f'{compiler}:/opt/devkitpro/devkitA64/bin:/opt/devkitpro/tools/bin:/usr/bin:/bin'
with tempfile.TemporaryDirectory(prefix='perf12-pe-',dir=root) as tmp:
    saved=[]
    for i,path in enumerate((source,obj,dll)):
        assert path.is_file(),path
        backup=Path(tmp)/str(i)
        shutil.copy2(path,backup)
        saved.append((path,backup))
    try:
        source.write_text(original[:start]+replacement+original[end:])
        subprocess.run(['make','-C',str(pe),'-j4','dlls/ntdll/aarch64-windows/ntdll.dll'],env=env,check=True)
        shutil.copy2(dll,dest/'ntdll-server-suspend.dll')
        asm=subprocess.check_output([str(compiler/'llvm-objdump'),'-dr',str(obj)],text=True)
        body=asm.split('<RtlWow64SuspendThread>:',1)[1].split('\n\n',1)[0]
        (dest/'suspend-disassembly.txt').write_text(body+'\n')
        # Reproduce the historical fallback when its extracted distribution
        # has been cleaned. Record this as a rebuilt fallback, not the exact
        # historical DLL (compiler/debug metadata may differ).
        tree=ast.parse((p/'tools/build-perf3-test.py').read_text())
        fallback=next(ast.literal_eval(node.value) for node in tree.body
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='fast_suspend' for t in node.targets))
        source.write_text(original[:start]+fallback+original[end:])
        subprocess.run(['make','-C',str(pe),'-j4','dlls/ntdll/aarch64-windows/ntdll.dll'],env=env,check=True)
        shutil.copy2(dll,dest/'ntdll-perf3-rollback.dll')
    finally:
        for path,backup in saved: shutil.copy2(backup,path)
    for path,backup in saved: assert path.read_bytes()==backup.read_bytes(),path
print('PERF12 ARM64 ntdll built; source and baseline PE artifacts restored',flush=True)
