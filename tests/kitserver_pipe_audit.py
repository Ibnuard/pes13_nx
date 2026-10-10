"""Read-only audit of the supplied kserv DLL's sequential pipe producers."""
import argparse,hashlib,json
from pathlib import Path
import capstone,pefile
from capstone import x86

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.dll.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    assert digest=='06a6fea90a0c4eedba6e2b3d205052f2f273cb9a7427fd01b66416efb4a31123'
    pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
    imports={i.address:i.name.decode() for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True;md.skipdata=True
    section=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
    ins=list(md.disasm(section.get_data(),base+section.VirtualAddress))
    def api(i):
        if i.mnemonic!='call':return None
        op=i.operands[0]
        return imports.get(op.mem.disp) if op.type==x86.X86_OP_MEM else None
    checks=[]
    for j,i in enumerate(ins):
        if api(i)!='CreatePipe':continue
        before=ins[j-8:j]
        assert any(a.mnemonic=='mov' and a.op_str=='edx, dword ptr [edi]' for a in before)
        assert any(a.mnemonic=='add' and a.op_str=='edx, edx' for a in before)
        assert any(a.mnemonic=='push' and a.op_str=='edx' for a in before)
        after=[a for a in ins[j+1:] if a.address<i.address+0x100]
        write=next(a for a in after if api(a)=='WriteFile')
        assert not any(api(a)=='ReadFile' for a in after if a.address<write.address)
        prepare=[a for a in after if write.address-32<=a.address<write.address]
        length_reg='ecx' if i.address-base==0xb39a else 'eax'
        assert any(a.mnemonic=='mov' and a.op_str==length_reg+', dword ptr [edi]' for a in prepare)
        pushes=[a.op_str for a in prepare if a.mnemonic=='push']
        assert pushes[-3]==length_reg
        publish={0xb39a:(0xb43e,'dword ptr [eax], edx'),
                 0xba2d:(0xbae0,'dword ptr [ecx], eax'),
                 0xc0fd:(0xc1b0,'dword ptr [ecx], eax')}[i.address-base]
        assert any(a.address-base==publish[0] and a.mnemonic=='mov' and a.op_str==publish[1]
                   for a in after if a.address>write.address)
        checks.append({'create_rva':hex(i.address-base),'write_rva':hex(write.address-base),
            'quota_multiplier':2,'read_before_write':False,'publish_handle_rva':hex(publish[0]),
            'create_setup':[a.mnemonic+' '+a.op_str for a in before],
            'write_setup':[a.mnemonic+' '+a.op_str for a in prepare]})
    assert [c['create_rva'] for c in checks]==['0xb39a','0xba2d','0xc0fd']
    report={'passed':True,'file_modified':False,'dll_sha256':digest,'checks':checks,
        'source_reference':'https://github.com/NiklasOff/kitserver/blob/4077d5ab1fa82c6f698d947e44bdd76d4dc06b27/src/kserv/kserv.cpp#L1833',
        'limits':'Static code inspection, not execution of the full plugin. The runtime log records the quota, not the originating DLL PC.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'dll_sha256':digest,'pipe_producers':len(checks)}))
if __name__=='__main__':main()
