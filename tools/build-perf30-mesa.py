"""Compile instrumented objects using existing exact compile flags into a private SDK."""
from pathlib import Path
import hashlib,json,os,shlex,shutil,subprocess,sys
from perf30_mesa import patch
from perf30_archive import members as archive_members, replace as replace_members
p=Path(__file__).resolve().parents[1];w=p/'local/perf30';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'mesa-switch';cross=root/'mesa-vulkan/cross'
sdk=root/'perf30-mesa-sdk';lib=sdk/'lib';lib.mkdir(parents=True,exist_ok=True)
stock=root/'mesa-vulkan/install/opt/devkitpro/portlibs/switch'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
assert pin=='b297e230ef88c6c88df2561becf864f979f494a6'
ar='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar'
archive=stock/'lib/libvulkan.a';original_hash=sha(archive)
members=subprocess.check_output([ar,'t',str(archive)],text=True).splitlines()
stock_members=archive_members(archive.read_bytes())
database=json.loads((cross/'compile_commands.json').read_text());records=[]
files=['src/nouveau/vulkan/nvk_queue.c','src/nouveau/vulkan/nvkmd/switch/nvkmd_switch_dev.c',
    'src/nouveau/horizon/nouveau_horizon_channel.c','src/vulkan/runtime/vk_queue.c']
for rel in files:
    src=source/rel;before=sha(src)
    entry=[e for e in database if (Path(e['directory'])/e['file']).resolve()==src];assert len(entry)==1,rel
    entry=entry[0];args=shlex.split(entry['command']);oldobj=Path(entry['output']).name
    # Unified static archive preserves the compiler's original object basename.
    compiled_original=Path(entry['directory'])/entry['output']
    original_object_hash=sha(compiled_original)
    candidates=[m for m,h in stock_members if m==oldobj and h==original_object_hash]
    assert candidates,(oldobj,'installed member differs from cached original object')
    generated=w/'mesa'/rel;generated.parent.mkdir(parents=True,exist_ok=True)
    generated.write_text(patch(src.name,src.read_text(),p))
    objdir=sdk/'objects';objdir.mkdir(exist_ok=True);obj=objdir/oldobj
    out=[];i=0
    while i<len(args):
        arg=args[i]
        if arg in ('-MF','-MQ','-o','-c'):i+=2;continue
        if arg=='-MD':i+=1;continue
        out.append(arg);i+=1
    out+=['-I'+str(src.parent),'-o',str(obj),'-c',str(generated)]
    if '--check' not in sys.argv: subprocess.run(out,cwd=entry['directory'],check=True)
    assert sha(src)==before
    records.append({'source':rel,'source_sha256':before,'generated':str(generated),
        'generated_sha256':sha(generated),'object':str(obj),'member':oldobj,
        'command':out,'directory':entry['directory'],'original_object_sha256':original_object_hash,
        'matching_members':len(candidates)})
if '--check' in sys.argv:
    print('PERF30 four source patch anchors and exact archive-member identities PASS');raise SystemExit(0)
for file in (stock/'lib').iterdir():
    if not file.is_file() or file.name=='libvulkan.a':continue
    target=lib/file.name
    if target.exists():assert target.is_symlink() and target.resolve()==file.resolve()
    else:target.symlink_to(file)
inc=sdk/'include'
if inc.exists():assert inc.is_symlink() and inc.resolve()==(stock/'include').resolve()
else:inc.symlink_to(stock/'include',target_is_directory=True)
private=lib/'libvulkan.a'
blob,counts=replace_members(archive.read_bytes(),{
    (r['member'],r['original_object_sha256']):Path(r['object']).read_bytes() for r in records})
private.write_bytes(blob)
subprocess.run(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ranlib',str(private)],check=True)
assert subprocess.check_output([ar,'t',str(private)],text=True).splitlines()==members
assert sha(archive)==original_hash
report={'stock_archive_sha256':original_hash,'private_archive_sha256':sha(private),
    'private_archive':str(private),'mesa_pin':pin,'records':records,'stock_untouched':True}
(w/'mesa-build.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF30 private Mesa archive built; original sources and SDK unchanged',flush=True)
