"""Verify the candidate changes only the reviewed allocation hooks in the frozen native adapter."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('adapter',type=Path);p.add_argument('frozen',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    changes=[
      ('#include "horizon_scratch_reserve.h"\n\nstatic void *allocate_scratch(uint64_t requested) {',
       'static void *allocate_scratch(uint64_t requested) {'),
      ('    void *result = fx_scratch_reserve_take(size);',
       '    void *result = aligned_alloc(PAGE_BYTES, size);'),
      ('static void release_scratch(void *address) { fx_scratch_reserve_release(address); }',
       'static void release_scratch(void *address) { free(address); }'),
      ('const struct pes13_fex_host *pes13_fex_native_host(void) {\n    fx_scratch_reserve_init();',
       'const struct pes13_fex_host *pes13_fex_native_host(void) {')]
    data=(a.adapter/'horizon_jit.c').read_text()
    pages=2 if '#define FX_SCRATCH_PAGES 2\n' in data else int('#define FX_SCRATCH_PAGES 1\n' in data)
    if pages:data=data.replace(f'#define FX_SCRATCH_PAGES {pages}\n','',1)
    if pages==2:
        changes += [
          ('    const size_t raw_size = (size_t)size + header_size + (size_t)alignment - 1;\n'
           '    void *raw = malloc(raw_size);\n'
           '#ifdef __SWITCH__\n'
           '    if (!raw && raw_size <= SIZE_MAX - (PAGE_BYTES - 1))\n'
           '        raw = fx_scratch_pages_take((raw_size + PAGE_BYTES - 1) & ~(size_t)(PAGE_BYTES - 1));\n'
           '#endif',
           '    void *raw = malloc((size_t)size + header_size + (size_t)alignment - 1);'),
          ('#ifdef __SWITCH__\n'
           '    if (fx_scratch_pages_release(header->allocation)) return;\n'
           '#endif\n'
           '    free(header->allocation);',
           '    free(header->allocation);')]
    reserve_mib=64 if '#define FX_SCRATCH_UNITS 8u\n' in data else 32
    if reserve_mib==64:data=data.replace('#define FX_SCRATCH_UNITS 8u\n','',1)
    for new,old in changes:
        assert data.count(new)==1,new
        data=data.replace(new,old)
    assert data==(a.frozen/'horizon_jit.c').read_text()
    original={str(f.relative_to(a.frozen)) for f in a.frozen.rglob('*') if f.is_file()}
    actual={str(f.relative_to(a.adapter)) for f in a.adapter.rglob('*') if f.is_file()}
    assert actual==original|{'horizon_scratch_reserve.h'}|({'horizon_scratch_pages.h'} if pages else set())
    for name in original-{'horizon_jit.c'}:
        assert sha(a.adapter/name)==sha(a.frozen/name),name
    assert sha(a.adapter/'horizon_scratch_reserve.h')==sha(ROOT/'src/fex/horizon_scratch_reserve.h')
    if pages:assert sha(a.adapter/'horizon_scratch_pages.h')==sha(ROOT/'src/fex/horizon_scratch_pages.h')
    result={'passed':True,'hardware_tested':False,'scratch_reserve_mib':reserve_mib,
            'checks':['Reversing the reviewed allocation hooks exactly reproduces frozen horizon_jit.c after newline normalization',
                      'Every other native adapter file remains byte-identical',
                      'Only the reviewed scratch reserve and optional page fallback headers are added'],
            'adapter_sources':{str(f.relative_to(a.adapter)).replace('\\','/'):sha(f) for f in sorted(a.adapter.rglob('*')) if f.is_file()},
            'sources':{'tests/fextendo_scratch_patches.py':sha(Path(__file__))}}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
