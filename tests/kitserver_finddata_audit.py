"""Read-only audit of the supplied AFS2FS 13.4 directory-index consumer.

No patched DLL is emitted. Fixed ranges are bound to the exact input hash.
The upstream source and the supplied DLL use the Find data's attributes/name
when constructing the BIN-name index, not its timestamp fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import capstone
from capstone import x86
import pefile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dll',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    digest=hashlib.sha256(a.dll.read_bytes()).hexdigest()
    assert digest=='d5f6cfa5438978c0ba57310fff67e1a7a8d167beffc93bee3cc6cc8dd4560c26'
    pe=pefile.PE(str(a.dll));base=pe.OPTIONAL_HEADER.ImageBase
    imports={i.address:i.name.decode() for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True
    assert imports[base+0x18004]=='FindFirstFileW' and imports[base+0x1801c]=='FindNextFileW'
    ins=list(md.disasm(pe.get_data(0x1fd2,0x2229-0x1fd2),base+0x1fd2))
    assert ins[0].address==base+0x1fd2 and ins[-1].address+ins[-1].size==base+0x2229
    accesses=[]
    for i in ins:
        for o in i.operands:
            if o.type==x86.X86_OP_MEM and o.mem.base==x86.X86_REG_EBP and -0x310<=o.mem.disp<-0x310+592:
                accesses.append({'rva':hex(i.address-base),'instruction':i.mnemonic+' '+i.op_str,
                                 'find_data_offset':o.mem.disp+0x310})
    assert {x['find_data_offset'] for x in accesses}=={0,44}
    assert accesses[0]['instruction']=='test byte ptr [ebp - 0x310], 0x10'
    assert all(x['instruction'].startswith('lea ') for x in accesses[1:])
    assert any(i.address==base+0x2215 and i.mnemonic=='call' and
               i.operands[0].type==x86.X86_OP_MEM and i.operands[0].mem.disp==base+0x1801c for i in ins)
    report={'passed':True,'dll_sha256':digest,'file_modified':False,
            'consumer':'AFS2FS InitializeFileNameCache inner file loop',
            'attribute_offset':0,'name_offset':44,'timestamp_range':[4,28],
            'direct_accesses':accesses,
            'upstream_reference':'https://github.com/NiklasOff/kitserver/blob/main/src/afs2fs/afs2fs.cpp#L229',
            'limits':'Static audit of the hash-bound consumer; not a full DLL/game execution or proof about other patch versions.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
