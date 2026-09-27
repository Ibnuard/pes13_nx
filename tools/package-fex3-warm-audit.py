"""Verified NRO-only warm-start logging fix and compilation/cache observer."""
import hashlib
import importlib.util
import json
from pathlib import Path
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/warm-start'
NRO = 'switch/pes13-fex/pes13-fex.nro'


def helper(name):
    spec = importlib.util.spec_from_file_location('helper', ROOT/'tools'/name)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def main():
    candidate, baseline = WORK/'runtime', ROOT/'local/fex3/hang-audit/runtime'
    read_json = lambda p: json.loads(p.read_text())
    new, old = read_json(candidate/'runtime-build.json'), read_json(baseline/'runtime-build.json')
    checked = helper('package-fex3-stability.py').checked
    for key in ('warm_audit','hang_audit','stability','samecore_yield','resume_gate','runtime_fixes','diagnostic'):
        if new.get(key) is not True: raise ValueError('Missing build flag: '+key)
    for key in ('adapter_sources','native_dependencies','toolchain_path','ntdll_sha256','wow64_sha256','guest_sha256'):
        if new[key]!=old[key]: raise ValueError('NRO-only dependency mismatch: '+key)
    for name,digest in new['adapter_sources'].items(): checked(ROOT/'src/fex'/name,digest)
    for name,digest in new['patch_sources'].items(): checked(ROOT/name,digest)
    a,b=read_json(candidate/'wine-patches.json'),read_json(baseline/'wine-patches.json')
    if a['pe-source']!=b['pe-source']: raise ValueError('PE source drift')
    delta=sorted(k for k in a['native-source'].keys()|b['native-source'].keys()
                 if a['native-source'].get(k)!=b['native-source'].get(k))
    if delta!=['dlls/winevulkan/vulkan_thunks.c','wine-nx-probe/CMakeLists.txt','wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native changes: '+repr(delta))
    for directory,receipt in ((candidate,new),(baseline,old)):
        for name,key in (('ntdll.dll','ntdll_sha256'),('wow64.dll','wow64_sha256'),('fex-stress.exe','guest_sha256')):
            checked(directory/'payload'/name,receipt[key])
    blob=checked(candidate/'payload/pes13-fex.nro',new['nro_sha256'])
    elf=candidate/'reference/pes13-fex.elf'
    checked(elf,new['native_elf_sha256'])
    helper('package-fex3-stability.py').verify_executable(elf,blob)
    metadata=inspect_nro(blob,(ROOT/'assets/icon.jpg').read_bytes(),
                         expected_title='PES13-NX FEX3',expected_version='0.3.0')
    if b'pes13-fex3-warm-audit' not in blob or b'[FEX3-WARM] v1' not in blob:
        raise ValueError('Wrong binary marker')
    if b'scaled present %d read back' in blob: raise ValueError('Diagnostic readback reintroduced')
    files={NRO:blob,'README.md':(ROOT/'docs/FEX3-WARM-AUDIT.md').read_bytes(),
           'evidence/log-analysis.json':(WORK/'log-analysis.json').read_bytes()}
    for name in ('warm-binary.json','pipeline-binary.json'):
        report=read_json(WORK/name)
        if report.get('passed') is not True or report.get('native_elf_sha256')!=new['native_elf_sha256']:
            raise ValueError('Invalid binary receipt: '+name)
        files['evidence/'+name]=(WORK/name).read_bytes()
    host=read_json(WORK/'host-validation.json')
    if host.get('passed') is not True or host.get('runtime_source_sha256')!=a['native-source']['wine-nx-probe/source/runtime.c']:
        raise ValueError('Host validation source mismatch')
    files['evidence/host-validation.json']=(WORK/'host-validation.json').read_bytes()
    for name in ('runtime-build.json','wine-patches.json'): files['evidence/'+name]=(candidate/name).read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt']=(ROOT/'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt']=(ROOT/'src/fex/LICENSE').read_bytes()
    for path in (ROOT/'licenses').rglob('*'):
        if path.is_file() and path.name!='Box64-LICENSE.txt': files[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    manifest={'kind':'Routine FEX flush batching and warm-start observer', 'hardware_tested':False,
              'stutter_fix_verified':False, 'replaces':[NRO], 'requires_existing_build':'pes13-fex3-hang-audit',
              'native_source_delta':delta,'native_elf_sha256':new['native_elf_sha256'], 'metadata':metadata,
              'files':{name:sha(data) for name,data in sorted(files.items())}}
    files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output=ROOT/'dist/pes13-fex3-warm-audit.zip'; folder=output.with_suffix('')
    if output.exists() or folder.exists(): raise FileExistsError('Preserve prior package')
    result=helper('package-fex3-runtime-fixes.py').write_overlay(output,files)
    folder.mkdir()
    for name,data in files.items():
        path=folder/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        if path.read_bytes()!=data: raise RuntimeError('Readback mismatch')
    (WORK/'package.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
