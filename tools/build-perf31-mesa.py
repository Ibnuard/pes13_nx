"""Instrument every linked archive copy, retaining unrelated members exactly."""
from pathlib import Path
import hashlib,json,os,shlex,subprocess,sys
from perf31_mesa import patch
from perf30_archive import members,replace
p=Path(__file__).resolve().parents[1];w=p/'local/perf31';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'mesa-switch';cross=root/'mesa-vulkan/cross';sdk=root/'perf31-mesa-sdk'
stock=root/'mesa-vulkan/install/opt/devkitpro/portlibs/switch';lib=sdk/'lib';lib.mkdir(parents=True,exist_ok=True)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()=='b297e230ef88c6c88df2561becf864f979f494a6'
db=json.loads((cross/'compile_commands.json').read_text())
records=[];replacements={}
for rel in ('src/nouveau/vulkan/nvk_queue.c','src/nouveau/vulkan/nvkmd/switch/nvkmd_switch_dev.c',
            'src/nouveau/horizon/nouveau_horizon_channel.c','src/vulkan/runtime/vk_queue.c',
            'src/vulkan/runtime/vk_sync_timeline.c'):
    src=source/rel;before=sha(src)
    entries=[e for e in db if (Path(e['directory'])/e['file']).resolve()==src];assert len(entries)==1,rel
    e=entries[0];args=shlex.split(e['command']);original=Path(e['directory'])/e['output']
    generated=w/'mesa'/rel;generated.parent.mkdir(parents=True,exist_ok=True);generated.write_text(patch(src.name,src.read_text(),p))
    obj=sdk/'objects'/original.name;obj.parent.mkdir(exist_ok=True)
    out=[];i=0
    while i<len(args):
        arg=args[i]
        if arg in ('-MF','-MQ','-o','-c'):i+=2;continue
        if arg=='-MD':i+=1;continue
        out.append(arg);i+=1
    out+=['-I'+str(src.parent),'-o',str(obj),'-c',str(generated)]
    subprocess.run(out,cwd=e['directory'],check=True)
    assert sha(src)==before
    replacements[(original.name,sha(original))]=obj.read_bytes()
    records.append(dict(source=rel,source_sha256=before,generated=str(generated),generated_sha256=sha(generated),
        object=str(obj),object_sha256=sha(obj),member=original.name,original_object_sha256=sha(original),command=out,directory=e['directory']))
archives=[];found=set()
for file in sorted((stock/'lib').iterdir()):
    if not file.is_file():continue
    target=lib/file.name
    matches={}
    if file.suffix=='.a':
        keys=set(members(file.read_bytes()));matches={key:data for key,data in replacements.items() if key in keys}
    if matches:
        assert not target.is_symlink(),target
        raw,counts=replace(file.read_bytes(),matches);target.write_bytes(raw)
        subprocess.run(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ranlib',str(target)],check=True)
        old=members(file.read_bytes());new=members(target.read_bytes());assert len(old)==len(new)
        changed=[]
        for a,b in zip(old,new):
            assert a[0]==b[0]
            if a in matches:
                assert b[1]==hashlib.sha256(matches[a]).hexdigest();changed.append(a[0]);found.add(a)
            else:assert a==b
        archives.append(dict(name=file.name,stock_sha256=sha(file),private_sha256=sha(target),changed=changed))
    elif target.exists():assert target.is_symlink() and target.resolve()==file.resolve()
    else:target.symlink_to(file)
assert found==set(replacements),(found,set(replacements))
inc=sdk/'include'
if inc.exists():assert inc.resolve()==(stock/'include').resolve()
else:inc.symlink_to(stock/'include',target_is_directory=True)
(w/'mesa-build.json').write_text(json.dumps(dict(records=records,archives=archives,stock_untouched=True),indent=2)+'\n')
print('PERF31 all archive copies built and unrelated members verified',[(x['name'],x['changed']) for x in archives],flush=True)
