"""Validate native Rust allocation contract with real mappings and sanitizers."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='fextendo-rust-heap-') as directory:
        d=Path(directory);binary=d/'test'
        (d/'fextendo_rust_symbols.h').write_text('''#include <stddef.h>
extern void *fx_rust_real_alloc(size_t,size_t);
extern void fx_rust_real_dealloc(void *,size_t,size_t);
extern void *fx_rust_real_realloc(void *,size_t,size_t,size_t);
extern void *fx_rust_real_alloc_zeroed(size_t,size_t);
''')
        subprocess.run(['gcc','-O1','-g','-std=c11','-pthread','-Wall','-Wextra','-fsanitize=address,undefined',
                        '-I'+str(d),str(ROOT/'tests/fextendo_rust_heap.c'),'-o',str(binary)],check=True)
        r=subprocess.run([str(binary)],capture_output=True,text=True);print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
    files=['src/fex/horizon_scratch_pages.h','src/runtime/fextendo_rust_heap.h','tests/fextendo_rust_heap.c',
           'tests/fextendo_rust_heap_host.py','tests/fextendo_scratch_pages.c']
    report={'passed':True,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'stdout':r.stdout,
            'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
