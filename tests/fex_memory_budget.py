"""Verify client-only filtering, generated-source scope and final build binding."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from fex_gap_probe import Model
from fextendo_source_normalization import undo_lsfg_vulkan

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if not __debug__:raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser();ap.add_argument('elf',type=Path)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();header=ROOT/'src/runtime/fex_memory_budget.h'
    source=a.source/'dlls/win32u/vulkan.c';text=source.read_text()
    call='    wine_nx_fex_filter_client_budget( &extensions );\n\n'
    assert text.count(header.read_text())==text.count(call)==1
    stripped=text.replace(header.read_text()+'\n','').replace(call,'')
    stripped,lsfg_normalization=undo_lsfg_vulkan(stripped,ROOT)
    baseline=json.loads((ROOT/'local/fex3/memory-audit/runtime/wine-patches.json').read_text())
    assert hashlib.sha256(stripped.encode()).hexdigest()==baseline['native-source']['dlls/win32u/vulkan.c']
    assert text.index('physical_device->extensions = extensions;')<text.index(call)<text.index('/* filter out unsupported client device extensions */')
    runtime=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    assert 'wine_nx_config_file_bool(RUNTIME_DIR "/fex_memory_budget", 0)' in runtime
    assert runtime.index('wine_nx_fex_memory_budget_enabled = wine_nx_config_file_bool')<runtime.index('wine_nx_runtime_platform_init();')
    # Reproduce Wine's actual extension bitfield layout for host and ELF checks.
    vk=(a.source/'include/wine/vulkan.h').read_text()
    def macro(name):
        lines=vk.splitlines();index=next(i for i,s in enumerate(lines) if s.startswith('#define '+name+' '))
        value=lines[index]
        while lines[index].endswith('\\'):
            index+=1;value+='\n'+lines[index]
        return value
    names=re.findall(r'USE_VK_EXT\((\w+)\)',macro('ALL_VK_CLIENT_DEVICE_EXTS')+macro('ALL_VK_DEVICE_EXTS'))
    assert len(names)==len(set(names)) and 'VK_EXT_memory_budget' in names
    code='#include <assert.h>\n#include <stdio.h>\n#include <string.h>\nstruct vulkan_device_extensions {\n'
    code+=''.join('unsigned has_'+n+':1;\n' for n in names)+'};\nint wine_nx_fex_memory_budget_enabled;\n'
    code+=header.read_text()+r'''
int main(void) {
    struct vulkan_device_extensions e,expected;
    memset(&e,255,sizeof(e));expected=e;expected.has_VK_EXT_memory_budget=0;
    wine_nx_fex_filter_client_budget(&e);assert(!memcmp(&e,&expected,sizeof(e)));
    wine_nx_fex_memory_budget_enabled=1;memset(&e,255,sizeof(e));expected=e;
    wine_nx_fex_filter_client_budget(&e);assert(!memcmp(&e,&expected,sizeof(e)));
    memset(&e,0,sizeof(e));wine_nx_fex_filter_client_budget(&e);assert(!e.has_VK_EXT_memory_budget);
    e.has_VK_EXT_memory_budget=1;assert(fwrite(&e,1,sizeof(e),stdout)==sizeof(e));
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'budget.c';exe=Path(tmp)/'budget';src.write_text(code)
        subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],check=True)
        mask=subprocess.check_output([str(exe)])
    assert sum(b.bit_count() for b in mask)==1
    model=Model(a.elf)
    # Release linking inlines the filter. Do not claim to execute a removed
    # function: bind sanitizer/source checks to the actual build receipt.
    assert bytes(model.vm.mem_read(model.symbols['wine_nx_fex_memory_budget_enabled'],4))==struct.pack('<I',0)
    receipt=json.loads((a.elf.parents[1]/'runtime-build.json').read_text())
    patches=json.loads((a.elf.parents[1]/'wine-patches.json').read_text())
    assert receipt['native_elf_sha256']==sha(a.elf) and receipt['memory_budget_filter']
    assert patches['native-source']['dlls/win32u/vulkan.c']==sha(source)
    assert receipt['patch_sources']['src/runtime/fex_memory_budget.h']==sha(header)
    if lsfg_normalization['applied']:
        assert receipt['lsfg']
        assert receipt['patch_sources']['tools/fextendo_lsfg_patches.py']==sha(ROOT/'tools/fextendo_lsfg_patches.py')
    paths=['tests/fex_memory_budget.py','src/runtime/fex_memory_budget.h','tools/fex_memory_budget_patches.py',
           'tests/fextendo_source_normalization.py','tools/fextendo_lsfg_patches.py']
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(a.elf),
            'checks':['Removing client filter and strictly reversing LSFG edits restores memory-audit Vulkan source exactly',
                      'Host extension record preserved; switch defaults OFF before platform initialization',
                      'Actual Wine bitfield layout under sanitizers: only the budget bit changes; opt-in restores capability',
                      'Final ELF defaults OFF; source and ELF hashes match build receipt (inlined filter not emulated)'],
            'source_hashes':{n:sha(ROOT/n) for n in paths},'generated_source_sha256':sha(source),
            'lsfg_source_normalization':lsfg_normalization}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print('Memory budget: PASS')
if __name__=='__main__':main()
