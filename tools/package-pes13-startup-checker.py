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
    build=json.loads((a.native/'build.json').read_text());assert build['built'] and build['version']=='0.4.1'
    nro=a.native/build['nro_filename'];assert sha(nro)==build['nro_sha256']
    assert sha(a.native/'native-build/wine-nx-runtime.elf')==build['elf_sha256']
    forwarder=json.loads((a.output/'forwarder-build.json').read_text())
    assert forwarder['runtime_nro_sha256']==build['nro_sha256'] and forwarder['abi']=='fxtmem-v1'
    assert forwarder['target']=='/switch/pes13-fex/pes13-fex.nro'
    assert forwarder['title_id']=='052d1913f51f5000' and forwarder['name']=='PES13-FEXTendo'
    assert forwarder['forwarder']['cnmt_version']==0x20000 and forwarder['automatic']
    assert forwarder['forwarder']['packed_cnmt_verified']
    metadata=json.loads((a.tests/'forwarder-metadata.json').read_text())
    assert metadata['passed'] and metadata['nsp_sha256']==forwarder['forwarder']['sha256']
    proofs=('startup-host.json','validation.json','lifecycle-host.json','fixer-host.json',
            'dependencies.json','memory-arm64.json','keyboard-arm64.json','hid-arm64.json','keyboard-host.json')
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
    copy(nro,'switch/pes13-fex/pes13-fex.nro')
    assert list((a.output/'switch').rglob('*.nro'))==[a.output/'switch/pes13-fex/pes13-fex.nro'],'Package contains an extra NRO'
    copy(a.native/'build.json','evidence/build.json');copy(a.native/'prepared.json','evidence/prepared.json')
    for n in proofs:copy(a.tests/n,'evidence/'+n)
    copy(a.tests/'forwarder-metadata.json','evidence/forwarder-metadata.json')
    for n in ('fextendo_runtime_download.txt','fextendo_startup_switch.txt','fextendo_ui.txt'):copy(a.tests/n,'evidence/'+n)
    for n in (28,29):
        src=a.tests/'preview'/('high-'+str(n)+'.png')
        if src.exists():copy(src,'evidence/high-'+str(n)+'.png')
    for n in range(4):
        src=a.tests/'preview'/('startup-'+str(n)+'.png')
        if src.exists():copy(src,'evidence/'+src.name)
    for n in (30,31,32):
        src=a.tests/'preview'/('keyboard-'+str(n)+'.png')
        if src.exists():copy(src,'evidence/'+src.name)
    sources.update(('tools/package-pes13-startup-checker.py','tools/runtime_fixer_catalog.py',
        'tools/verify-pes13-39bit-dependencies.py','tools/build-pes13-39bit-forwarder.py',
        'tools/build-fextendo-memory-probe.py','tools/fextendo_nsp_version.py',
        'tests/pes13_forwarder_metadata.py','tests/fextendo_checker_hid_binary.py',
        'tools/fextendo_low_window.py','src/experimental/low_window/fextendo_memory_abi.hpp',
        'src/experimental/low_window/forwarder_auto.inc'))
    for n in sorted(sources):copy(ROOT/n,'source/'+n)
    for n,h in build['source_changes'].items():
        src=a.native/'native-source'/n;assert sha(src)==h,n;copy(src,'source/generated/'+n)
    for n,h in build['feature_changes'].items():
        src=a.native/'feature'/n;assert sha(src)==h,n;copy(src,'source/generated-feature/'+n)
    for n in ('LICENSE','THIRD_PARTY.md','docs/PES13-39BIT-PATCH.md'):copy(ROOT/n,n)
    for src in (ROOT/'licenses').glob('*'):
        if src.is_file():copy(src,'licenses/'+src.name)
    (a.output/'README.txt').write_text(
        'FEXTendo 0.4.1 Auto - One game forwarder / selectable keyboard delay\n\n'
        '1. Close PES13. Back up the old NRO if needed. Copy switch/ to the SD root.\n'
        '   The only NRO is /switch/pes13-fex/pes13-fex.nro. Game and saves are not included.\n'
        '2. Game location: /switch/pes13-fex/drive_c/PES13/pes2013.exe\n'
        '   Its complete img folder must be alongside the executable.\n'
        '   Localized dt00_*.img and dt05_*.img are accepted; dt00.img is not required.\n'
        '   Shared AFS data archives are checked for missing files and truncated entries.\n'
        '3. Install forwarders/PES13-FEXTendo.nsp to UPDATE the existing tile.\n'
        '   It keeps Title ID 052d1913f51f5000 and changes the NRO target and display name.\n'
        '   CNMT installation revision is now 131072 (r2 used 65536).\n'
        '   The actual control NCA names all 16 languages PES13-FEXTendo, without 39-bit.\n'
        '   Allow your installer to update the existing title; do not only copy the NSP to SD.\n'
        '   If HOME still shows an old name, check the installer result/title ID;\n'
        '   the NRO does not rename a HOME tile. Game files and saves need no deletion.\n'
        '   The old 39-bit NSP still targets pes13-39bit.nro; renaming that file alone\n'
        '   cannot fix it. Replace the NSP first, then remove the obsolete pes13-39bit.nro.\n'
        '4. Without FEXTendo Patch: this SAME NSP uses 32-bit no-alias, with Low/Medium.\n'
        '   With FEXTendo Patch 1.1.0: this SAME NSP automatically uses 39-bit low-window.\n'
        '   Install the separate updated FEXTendo Patch NRO, apply its supported bundle,\n'
        '   then reboot via its Hekate boot entry once to activate the new loader.\n'
        '   An older 1.0.0 patch also falls back to 32-bit with this NSP. No title list.\n'
        '   HIGH unlocks only after the live 39-bit memory probe passes.\n'
        '   Homebrew/generic or ordinary 39-bit layouts cannot launch Wine.\n\n'
        'After the embedded FEXTendo splash, a blocking GUI popup checks installation,\n'
        'runtime and active memory-patch capability before opening the launcher.\n'
        'Missing/changed runtime files trigger automatic repair from the pinned official\n'
        'v0.3.8-r9 GitHub release, verified by package and per-file SHA256.\n'
        'A successful check is saved in launcher/startup-verified.dat. Later launches\n'
        'reuse it after quick metadata checks; full SHA scans do not repeat each launch.\n'
        'A new checker/catalog, changed installation anchors or interrupted repair\n'
        'invalidates it. Boot-patch admission is always tested anew. Cached checks\n'
        'do not detect every edited runtime file. Use Settings > Maintenance > Check\n'
        'runtime after manually changing files or if startup fails. It forces a rescan.\n'
        'Healthy runtime works offline. Repair needs Wi-Fi, a correct date and about\n'
        '300 MB free SD space. The active popup cannot be dismissed into Play/Settings.\n'
        'On failure, A retries and B / + closes the launcher. HOME still closes the app.\n'
        'Allow an installation commit to finish before powering off.\n'
        'Game/patch files, saves, registry, preferences, active renderer configs and NRO\n'
        'are excluded from repair. No automatic logs or in-game background scanning.\n'
        'Normal launch remains production; only Debug launch enables diagnostic files.\n'
        'The owner confirmed the kickoff failure came from bad dt09 data. The temporary\n'
        'asset-origin diagnostics have been removed; original r6 FEX/gameplay is retained.\n'
        'Settings > Keyboard > Activation delay: Instant (default), 0.3, 0.6, 1, 1.5 or\n'
        '2 seconds. Existing shortcut/position preferences are preserved. Player 1 only;\n'
        'release and press the combo again to rearm. Player 2 cannot open/use the OSK.\n\n'
        'Build, host HTTPS/repair/recovery/UI/lifecycle and actual ARM64 memory/OSK\n'
        'tests passed. Kernel/HID/VI are modeled in ARM64 tests. Switch Wi-Fi/TLS,\n'
        'automatic 32/39 launch, boot-patch detection, SD repair and gameplay still need\n'
        'device testing. No performance gain or new RAM capacity is promised by this build.\n',encoding='utf-8')
    manifest={'version':build['version'],'passed':True,'hardware_tested':False,
        'build_revision':build.get('build_revision'),'forwarder_cnmt_version':forwarder['forwarder']['cnmt_version'],
        'nro_sha256':build['nro_sha256'],'native_elf_sha256':build['elf_sha256'],
        'repair_release':'v0.3.8-r9','catalog_file_count':221,
        'files':{p.relative_to(a.output).as_posix():sha(p) for p in a.output.rglob('*') if p.is_file() and p.name!='manifest.json'}}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for n,h in manifest['files'].items():assert sha(a.output/n)==h,n
    print(json.dumps({'package':str(a.output),'verified_files':len(manifest['files']),'nro_sha256':build['nro_sha256']}))
if __name__=='__main__':main()
