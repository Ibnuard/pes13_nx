"""Build the pinned Kit17 x86 D3D9 DLL without changing the native/FEX runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from dxvk_kit17_memory import COMMIT, apply

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'work', 'toolchain', 'shader-tools'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=3)
    a = ap.parse_args()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(a.upstream), *args], text=True).strip()
    assert git('rev-parse', 'HEAD') == COMMIT
    assert not git('status', '--porcelain', '--untracked-files=all')
    subs = git('submodule', 'status', '--recursive')
    assert subs and all(not line.startswith(('-', '+', 'U')) for line in subs.splitlines())
    source, build = a.work/'source', a.work/'build'
    assert not a.work.exists(), 'Use a fresh work directory; no source is reset'
    a.work.mkdir(parents=True)
    shutil.copytree(a.upstream, source, ignore=shutil.ignore_patterns('.git'))
    before = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob('*') if p.is_file()}
    changes = apply(source)
    after = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob('*') if p.is_file()}
    assert before.keys() == after.keys()
    assert set(n for n in before if before[n] != after[n]) == set(changes)
    scripts = {str(p.relative_to(ROOT)): sha(p) for p in
               (Path(__file__), ROOT/'tools/dxvk_kit17_memory.py')}
    prepared = dict(commit=COMMIT, submodules=subs, original=before, candidate=after,
                    changes=changes, scripts=scripts)
    (a.work/'prepared.json').write_text(json.dumps(prepared, indent=2)+'\n')
    tc = a.toolchain/'bin'
    cross = a.work/'cross-x32.txt'
    names = dict(c='clang', cpp='clang++', ar='ar', strip='strip', windres='windres')
    cross.write_text('[binaries]\n' + ''.join(
        f"{role} = '{tc}/i686-w64-mingw32-{tool}'\n" for role, tool in names.items()) +
        "[properties]\nneeds_exe_wrapper = true\n[host_machine]\nsystem = 'windows'\n"
        "cpu_family = 'x86'\ncpu = 'x86'\nendian = 'little'\n")
    env = dict(os.environ, PATH=str(a.shader_tools)+':'+str(tc)+':'+os.environ['PATH'])
    def run(cmd):
        subprocess.run(list(map(str,cmd)), env=env, check=True)
    run(['meson','setup',build,source,'--cross-file',cross,'--buildtype=release',
         '-Ddebug=true','-Denable_d3d8=false','-Denable_d3d10=false',
         '-Denable_d3d11=false','-Denable_dxgi=false','-Dbuild_id=true','--wrap-mode=nodownload'])
    run(['ninja','-C',build,'-j',str(a.jobs)])
    compiled = build/'src/d3d9/d3d9.dll'
    run([tc/'i686-w64-mingw32-strip','--strip-debug','-o',a.work/'d3d9.dll',compiled])
    assert b'pes13-kit17' in (a.work/'d3d9.dll').read_bytes()
    for n, digest in after.items(): assert sha(source/n) == digest, n
    report = dict(built=True, kind='kit17-dxvk-memory', commit=COMMIT,
        dll_sha256=sha(a.work/'d3d9.dll'), dll_bytes=(a.work/'d3d9.dll').stat().st_size,
        unstripped_sha256=sha(compiled), prepared_sha256=sha(a.work/'prepared.json'),
        compiler=subprocess.check_output([str(tc/'i686-w64-mingw32-clang++'),'--version'],text=True).splitlines()[0],
        scripts=scripts)
    (a.work/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
