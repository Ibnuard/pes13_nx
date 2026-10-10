"""Build Kit16 against the verified Kit6 module used by Kit7--15."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from fex_decoder_capacity_patches import apply
from fex_toolchain import cmake_provenance

PIN = 'e2f973fe931e6dc2ce523795e51ca1ac3ca85816'
BASE = 'a77a4cced1d8e26198a29cd33311c8ecdcfa0480aaeaba7adf9b7b705b8f9ed3'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'receipt', 'work', 'output', 'toolchain'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    b = json.loads(a.receipt.read_text())
    assert b['built'] and b['dll_sha256'] == BASE and b['fex_commit'] == PIN
    assert sha(a.baseline/'build/Bin/libwow64fex.dll') == BASE
    expected = b['frozen_sources'] | b['candidate_sources']
    for name, digest in expected.items():
        assert sha(a.baseline/'source'/name) == digest, name
    for name, digest in b['adapter_sources'].items():
        assert sha(a.baseline/'adapter'/name) == digest, name
    source, adapter, build = (a.work/n for n in ('source','adapter','build'))
    a.output.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        shutil.copytree(a.baseline/'source', source, symlinks=True)
        shutil.copytree(a.baseline/'adapter', adapter, symlinks=True)
    # Restore all scoped inputs before applying, making an interrupted build
    # repeatable without reapplying text changes to an already-patched file.
    paths = ['FEXCore/Source/Interface/Core/Frontend.cpp',
             'FEXCore/Source/Interface/Core/Frontend.h', 'Source/Windows/WOW64/Module.cpp']
    for name in paths:
        shutil.copy2(a.baseline/'source'/name, source/name)
        before = a.work/'before'/name
        before.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source/name, before)
    changed = apply(source)
    assert changed == set(paths)
    # Confirm no other file or adapter changed, including previously unpatched
    # FEX sources. Compare the entire source tree to the delivered build input.
    baseline_tree = {p.relative_to(a.baseline/'source').as_posix():sha(p)
                     for p in (a.baseline/'source').rglob('*') if p.is_file()}
    candidate_tree = {p.relative_to(source).as_posix():sha(p)
                      for p in source.rglob('*') if p.is_file()}
    assert baseline_tree.keys() == candidate_tree.keys()
    assert {n for n in baseline_tree if baseline_tree[n]!=candidate_tree[n]} == changed
    for name,digest in b['adapter_sources'].items(): assert sha(adapter/name)==digest,name
    report = dict(kind='kit16-decoder-capacity', fex_commit=PIN,
        baseline_dll_sha256=BASE, baseline_sources=expected,
        baseline_changed_sources={n:sha(a.baseline/'source'/n) for n in paths},
        candidate_sources={n:sha(source/n) for n in paths},
        full_source_tree_sha256=hashlib.sha256(json.dumps(candidate_tree,sort_keys=True).encode()).hexdigest(),
        source_file_count=len(candidate_tree), adapter_sources=b['adapter_sources'],
        build_scripts={Path(__file__).name:sha(Path(__file__)),
            'fex_decoder_capacity_patches.py':sha(Path(__file__).with_name('fex_decoder_capacity_patches.py'))},
        hardware_tested=False, scope='Only decoder workspace capacity and release bounds; same IR size, profile and block limits.')
    (a.output/'source-report.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.prepare_only:
        print(json.dumps({'prepared':str(source),'changed':sorted(changed)}),flush=True)
        return
    cmake_provenance(build, a.toolchain)
    env = dict(os.environ, PATH=str(a.toolchain/'bin')+os.pathsep+os.environ['PATH'])
    def run(cmd):
        print('+',' '.join(map(str,cmd)),flush=True)
        subprocess.run(list(map(str,cmd)),env=env,check=True)
    run(['cmake','-S',source,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_TOOLCHAIN_FILE='+str(source/'Data/CMake/toolchain_mingw.cmake'),
        '-DMINGW_TRIPLE=aarch64-w64-mingw32','-DENABLE_LTO=OFF','-DBUILD_TESTING=OFF',
        '-DENABLE_JEMALLOC_GLIBC_ALLOC=OFF','-DENABLE_ASSERTIONS=OFF','-DENABLE_CCACHE=OFF',
        '-DENABLE_OFFLINE_TELEMETRY=OFF','-DENABLE_GDB_SYMBOLS=OFF','-DRANGES_NATIVE=OFF',
        '-DTUNE_CPU=cortex-a57','-DTUNE_ARCH=armv8-a','-DOVERRIDE_VERSION=pes13-nx-fex1',
        '-DOVERRIDE_HASH='+PIN,'-DPES13_HORIZON_DIR='+str(adapter)])
    run(['cmake','--build',build,'--target','wow64fex','-j',a.jobs])
    dll=build/'Bin/libwow64fex.dll'
    shutil.copy2(dll,a.output/dll.name)
    report.update(built=True,dll_sha256=sha(dll),dll_bytes=dll.stat().st_size,
                  compiler_provenance=cmake_provenance(build,a.toolchain,required=True))
    (a.output/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'built':str(dll),'sha256':sha(dll)}),flush=True)


if __name__=='__main__': main()
