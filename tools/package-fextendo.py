"""Package Fextendo with exact gap-audit rollback and verified source receipts."""
from pathlib import Path
import hashlib, importlib.util, json, struct, zipfile, binascii

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'local/fex3/fextendo'
NRO='switch/pes13-fex/pes13-fex.nro'
BASE_SHA='f533b7fd5f8431720f2ae800f3303b81600fd226bd113977adbb98018f9fbb4c'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(x):return (json.dumps(x,indent=2)+'\n').encode()
def read(p):return json.loads(p.read_text())
def checked(p,h):
    b=p.read_bytes()
    if sha(b)!=h:raise ValueError('Hash mismatch '+str(p))
    return b

def main():
    base=ROOT/'dist/pes13-fex3-gap-audit.zip';checked(base,BASE_SHA)
    files={}
    with zipfile.ZipFile(base) as z:
        manifest=json.loads(z.read('manifest.json'))
        if z.testzip() or set(z.namelist())!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Baseline ZIP inventory')
        for n,h in manifest['files'].items():
            b=z.read(n)
            if sha(b)!=h:raise ValueError('Baseline member '+n)
            if n.startswith('switch/'):files[n]=files['rollback/'+n]=b
            elif n.startswith(('source/','evidence/')):
                prefix,rest=n.split('/',1);files[prefix+'/gap-audit/'+rest]=b
            elif n.startswith(('licenses/','benchmark/')) or n=='THIRD_PARTY.md':files[n]=b
        files['evidence/gap-audit/manifest.json']=z.read('manifest.json')
    new=read(WORK/'runtime/runtime-build.json');old=json.loads(files['evidence/gap-audit/runtime/runtime-build.json'])
    for k in ('native_dependencies','adapter_sources','ntdll_sha256','wow64_sha256','guest_sha256','toolchain_path'):
        if new[k]!=old[k]:raise ValueError('Unexpected dependency change '+k)
    if not new['launcher'] or not new['gap_audit'] or new['yield_adaptive']:raise ValueError('Wrong build profile')
    for n,h in new['patch_sources'].items():checked(ROOT/n,h)
    for n,h in new['adapter_sources'].items():checked(ROOT/'src/fex'/n,h)
    patches=read(WORK/'runtime/wine-patches.json');previous=json.loads(files['evidence/gap-audit/runtime/wine-patches.json'])
    if patches['pe-source']!=previous['pe-source']:raise ValueError('PE delta')
    delta=sorted(n for n in patches['native-source'].keys()|previous['native-source'].keys()
                 if patches['native-source'].get(n)!=previous['native-source'].get(n))
    if delta!=['wine-nx-probe/source/runtime.c']:raise ValueError('Native delta '+repr(delta))
    nro=checked(WORK/'runtime/payload/pes13-fex.nro',new['nro_sha256'])
    elf=WORK/'runtime/reference/pes13-fex.elf';checked(elf,new['native_elf_sha256'])
    spec=importlib.util.spec_from_file_location('stable',ROOT/'tools/package-fex3-stability.py')
    stable=importlib.util.module_from_spec(spec);spec.loader.exec_module(stable);stable.verify_executable(elf,nro)
    for marker in (b'pes13-fextendo-v1',b'[FEXTENDO]',b'Launch failed',b'Fextendo',b'by AndroSwitch Project',b'[FEX3-GAP] v1'):
        if marker not in nro:raise ValueError('Missing launcher marker '+str(marker))
    files[NRO]=nro
    active_settings=[n for n in files if n.startswith('switch/') and n.endswith('/settings.dat')]
    if len(active_settings)!=3:raise ValueError('Settings inventory')
    preset_root=ROOT/'config/fextendo/presets';presets=read(preset_root/'presets.json')
    for name,meta in presets.items():
        b=checked(preset_root/(name+'.dat'),meta['sha256'])
        if len(b)!=852 or struct.unpack_from('<HIIIII',b,14)!=(0x289,meta['width'],meta['height'],1,meta['quality_word'],1):raise ValueError('Preset fields')
        zeroed=bytearray(b);zeroed[12:14]=b'\0\0'
        if struct.unpack_from('<H',b,12)[0]!=(~binascii.crc_hqx(zeroed,0)&65535):raise ValueError('Preset checksum')
        if b[32:]!=files['rollback/'+active_settings[0]][32:]:raise ValueError('Unrelated preset data changed')
    medium=(preset_root/'medium-720.dat').read_bytes()
    for n in active_settings:files[n]=medium
    files['switch/pes13-fex/drive_c/PES13/dxvk.conf']=(preset_root/'dxvk.conf').read_bytes()
    def pairs(b):return dict(line.split('=',1) for line in b.decode().splitlines() if '=' in line and not line.startswith('#'))
    before=pairs(files['rollback/switch/pes13-fex/drive_c/PES13/dxvk.conf']);after=pairs(files['switch/pes13-fex/drive_c/PES13/dxvk.conf'])
    if {k for k in before|after if before.get(k)!=after.get(k)}!={'d3d9.presentInterval '}:raise ValueError('DXVK changed beyond VSync')
    artroot=WORK/'package/switch/pes13-fex/launcher';art=read(artroot/'assets.json')
    for n,h in art['inputs'].items():checked(ROOT/n,h)
    for n,h in art['files'].items():files['switch/pes13-fex/launcher/'+n]=checked(artroot/n,h)
    files['switch/pes13-fex/launcher/assets.json']=(artroot/'assets.json').read_bytes()
    files['switch/pes13-fex/launcher/selected.txt']=b'0\n'
    for p in preset_root.iterdir():files['switch/pes13-fex/launcher/presets/'+p.name]=p.read_bytes()
    sources=set(new['patch_sources'])|{'src/fex/'+n for n in new['adapter_sources']}|set(art['inputs'])
    checks=('launcher','gap','balance','yield','cores','resume','pipeline','jit-log','unwind')
    for name in checks:
        p=WORK/(name+'.json');r=read(p)
        if r.get('passed') is not True or r['native_elf_sha256']!=new['native_elf_sha256']:raise ValueError('Stale test '+name)
        for n,h in r.get('source_hashes',r.get('source_sha256',{})).items():checked(ROOT/n,h);sources.add(n)
        files['evidence/'+name+'.json']=p.read_bytes()
    for n in ('runtime-build.json','wine-patches.json'):files['evidence/runtime/'+n]=(WORK/'runtime'/n).read_bytes()
    generated=Path(new['native_source'])/'source/runtime.c'
    files['source/generated/runtime.c']=checked(generated,patches['native-source']['wine-nx-probe/source/runtime.c'])
    sources|={'tools/package-fextendo.py','docs/FEXTENDO-LAUNCHER.md','tools/build-fextendo-assets.py','tools/make-fextendo-presets.py','tests/run_fextendo_checks.py'}
    sources|={p.relative_to(ROOT).as_posix() for p in preset_root.iterdir()}
    for n in sources:files['source/'+n]=(ROOT/n).read_bytes()
    files['licenses/Barlow-OFL.txt']=(ROOT/'assets/fonts/OFL.txt').read_bytes()
    files['README.md']=(ROOT/'docs/FEXTENDO-LAUNCHER.md').read_bytes()
    files['THIRD_PARTY.md']=(ROOT/'THIRD_PARTY.md').read_bytes()
    files['source/assets/README.md']=(ROOT/'assets/README.md').read_bytes()
    for n in (0,1,2,4,5):
        p=WORK/f'preview/screen-{n}.png'
        if p.exists():files[f'preview/screen-{n}.png']=p.read_bytes()
    result={'kind':'fextendo-v1','baseline_zip_sha256':BASE_SHA,'hardware_tested':False,
            'native_elf_sha256':new['native_elf_sha256'],'nro_sha256':new['nro_sha256'],
            'default':'Medium 720p','vsync':True,'settings_primary':'C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat',
            'quality_mapping_verified':False,'native_changed':delta,'checks':list(checks),
            'files':{n:sha(b) for n,b in sorted(files.items())}}
    files['manifest.json']=enc(result)
    folder=ROOT/'dist/pes13-fextendo-launcher';archive=folder.with_suffix('.zip')
    if folder.exists() or archive.exists():raise FileExistsError('Existing artifact protected')
    for n,b in files.items():p=folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or len(z.namelist())!=len(files):raise ValueError('Final ZIP inventory')
        for n,b in files.items():
            if z.read(n)!=b:raise ValueError('Final ZIP mismatch '+n)
    print(json.dumps({'passed':True,'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'files':len(files)},indent=2))

if __name__=='__main__':main()
