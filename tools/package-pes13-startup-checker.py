"""Seal a copy-ready original startup-checker overlay and its verified forwarder."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('native','tests','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();a.output.resolve().relative_to((ROOT/'dist').resolve())
    assert a.output.resolve()!= (ROOT/'dist').resolve()
    build=json.loads((a.native/'build.json').read_text());assert build['built'] and build['version']=='0.4.0'
    nro=a.native/build['nro_filename'];assert sha(nro)==build['nro_sha256']
    assert sha(a.native/'native-build/wine-nx-runtime.elf')==build['elf_sha256']
    forwarder=json.loads((a.output/'forwarder-build.json').read_text())
    assert forwarder['runtime_nro_sha256']==build['nro_sha256'] and forwarder['abi']=='fxtmem-v1'
    proofs=('startup-host.json','validation.json','lifecycle-host.json','fixer-host.json',
            'dependencies.json','memory-arm64.json','keyboard-arm64.json','hid-arm64.json')
    sources=set(build['input_sources'])
    for n,h in build['input_sources'].items():assert sha(ROOT/n)==h,n
    for n in proofs:
        proof=json.loads((a.tests/n).read_text());assert proof['passed'],n
        for key in ('elf_sha256','native_elf_sha256'):
            if key in proof:assert proof[key]==build['elf_sha256'],n
        for name,h in proof.get('sources',{}).items():assert sha(ROOT/name)==h; sources.add(name)
    assert json.loads((a.tests/'validation.json').read_text())['https_tested']
    def copy(src,name):
        dest=a.output/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    for name in ('pes13-39bit.nro','pes13-fex.nro'):copy(nro,'switch/pes13-fex/'+name)
    copy(a.native/'build.json','evidence/build.json');copy(a.native/'prepared.json','evidence/prepared.json')
    for n in proofs:copy(a.tests/n,'evidence/'+n)
    for n in ('fextendo_runtime_download.txt','fextendo_startup_switch.txt','fextendo_ui.txt'):copy(a.tests/n,'evidence/'+n)
    for n in (28,29):
        src=a.tests/'preview'/('high-'+str(n)+'.png')
        if src.exists():copy(src,'evidence/high-'+str(n)+'.png')
    sources.update(('tools/package-pes13-startup-checker.py','tools/runtime_fixer_catalog.py',
        'tools/verify-pes13-39bit-dependencies.py','tools/build-pes13-39bit-forwarder.py','tests/fextendo_checker_hid_binary.py'))
    for n in sorted(sources):copy(ROOT/n,'source/'+n)
    for n,h in build['source_changes'].items():
        src=a.native/'native-source'/n;assert sha(src)==h,n;copy(src,'source/generated/'+n)
    for n,h in build['feature_changes'].items():
        src=a.native/'feature'/n;assert sha(src)==h,n;copy(src,'source/generated-feature/'+n)
    for n in ('LICENSE','THIRD_PARTY.md','docs/PES13-39BIT-PATCH.md'):copy(ROOT/n,n)
    for src in (ROOT/'licenses').glob('*'):
        if src.is_file():copy(src,'licenses/'+src.name)
    (a.output/'README.txt').write_text(
        'FEXTendo 0.4.0 - Automatic startup checks\n\n'
        '1. Close PES13. Back up the old NRO if needed. Copy switch/ to the SD root.\n'
        '   Both NRO filenames contain the same checker. Game and saves are not included.\n'
        '2. Game location: /switch/pes13-fex/drive_c/PES13/pes2013.exe\n'
        '   Its complete img folder must be alongside the executable.\n'
        '3. For HIGH: boot FEXTendo Patch, install forwarders/PES13-FEXTendo-39bit.nsp,\n'
        '   then use PES13 FEXTendo 39-bit from HOME. The v1 forwarder also works.\n'
        '   The existing 32-bit no-alias HOME tile supports Medium/Low with the new NRO.\n'
        '   Homebrew/generic or ordinary 39-bit layouts cannot launch Wine.\n\n'
        'Startup checks validate installation, runtime and active memory-patch capability.\n'
        'Missing/changed runtime files trigger automatic repair from the pinned official\n'
        'v0.3.8-r9 GitHub release, verified by package and per-file SHA256.\n'
        'Healthy runtime works offline. Repair needs Wi-Fi, a correct date and about\n'
        '300 MB free SD space. B / + cancels; an active commit finishes safely.\n'
        'Incorrect installation or repair errors show a popup and Retry/Close screen.\n'
        'Game/patch files, saves, registry, preferences, active renderer configs and NRO\n'
        'are excluded from repair. No automatic logs or in-game background scanning.\n'
        'Normal launch remains production; only Debug launch enables diagnostic files.\n'
        'OSK retains the Player 1-only shortcut and input fix.\n\n'
        'Build, host HTTPS/repair/recovery/UI/lifecycle and actual ARM64 memory/OSK\n'
        'tests passed. Kernel/HID/VI are modeled in ARM64 tests. Switch Wi-Fi/TLS,\n'
        'boot-patch detection, SD repair and gameplay still need device testing.\n',encoding='utf-8')
    manifest={'version':build['version'],'passed':True,'hardware_tested':False,
        'nro_sha256':build['nro_sha256'],'native_elf_sha256':build['elf_sha256'],
        'repair_release':'v0.3.8-r9','catalog_file_count':221,
        'files':{p.relative_to(a.output).as_posix():sha(p) for p in a.output.rglob('*') if p.is_file() and p.name!='manifest.json'}}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for n,h in manifest['files'].items():assert sha(a.output/n)==h,n
    print(json.dumps({'package':str(a.output),'verified_files':len(manifest['files']),'nro_sha256':build['nro_sha256']}))
if __name__=='__main__':main()
