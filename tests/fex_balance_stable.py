"""Exercise incremental placement and the actual linked ARM64 balancer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from fex_worker_cores import Model
from fex_resume_gate import function
from fextendo_source_normalization import undo_polling

ROOT = Path(__file__).resolve().parents[1]
CASE = [(208,1),(125,2),(10,0),(47,2),(32,0),(229,0),
        (90,0),(37,0),(132,0),(231,1),(158,0),(31,0)]


def native(source):
    code = '#include <stddef.h>\n#include "'+str(source/'wine-nx-probe/source/thread_profile.h')+'"\n'
    code += '#include "'+str(ROOT/'src/runtime/fex_balance_stable.h')+'"\n'
    code += r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned random_state=29;
static unsigned random32(void) { return random_state=random_state*1664525u+1013904223u; }
static unsigned moves(struct nx_balance_thread *t,unsigned n) {
  unsigned count=0;for(unsigned i=0;i<n;i++)count+=t[i].new_core>=0 && t[i].new_core!=t[i].core;return count;
}
int main(void) {
  unsigned before,after;
  struct nx_balance_thread tie[]={{600,0,0,0},{200,0,0,0},{0,1,0,0}};
  after=fex_balance_stable(tie,3,2,&before);
  assert(before==800 && after==600 && tie[0].new_core==0 && tie[1].new_core==1);
  /* A fixed dominant core must not prevent relieving a secondary one. */
  struct nx_balance_thread secondary[]={{1000,0,1,0},{400,1,0,0},{300,1,0,0},{100,2,0,0}};
  after=fex_balance_stable(secondary,4,3,&before);
  assert(before==1000 && after==1000 && secondary[2].new_core==2 && moves(secondary,4)==1);
  /* Exactly 5 percentage points is insufficient, and an unknown fixed mask stays. */
  struct nx_balance_thread edge[]={{600,0,1,0},{50,0,0,0},{100,1,1,0},{800,-1,1,0}};
  fex_balance_stable(edge,4,2,&before);assert(!moves(edge,4));
  struct nx_balance_thread urgent[]={{650,0,1,0},{200,1,0,0},{150,2,0,0},{437,-1,0,0},{438,-1,1,0}};
  fex_balance_stable(urgent,5,3,&before);
  assert(urgent[3].new_core==2 && urgent[4].new_core==-1 && moves(urgent,5)==1);
  assert(fex_balance_stable(urgent,5,0,&before)==0 && !moves(urgent,5));
  /* Property checks: one move, eligible destination, fixed/light preservation,
   * genuine pair improvement, exact projected load, no repeated churn at rest. */
  for(unsigned k=0;k<20000;k++) {
    struct nx_balance_thread t[128];unsigned n=random32()%129,cores=1+random32()%8,loads[8]={0};
    for(unsigned i=0;i<n;i++) {
      t[i]=(struct nx_balance_thread){random32()%1001,(int)(random32()%cores),(int)(random32()%5==0),-1};
      loads[t[i].core]+=t[i].load;
    }
    after=fex_balance_stable(t,n,cores,&before);assert(moves(t,n)<=1 && after<=before);
    for(unsigned i=0;i<n;i++) {
      assert(t[i].new_core>=0 && (unsigned)t[i].new_core<cores);
      if(t[i].fixed || t[i].load<NX_BALANCE_LIGHT)assert(t[i].new_core==t[i].core);
      if(t[i].new_core!=t[i].core) {
        unsigned a=loads[t[i].core],b=loads[t[i].new_core],x=a-t[i].load,y=b+t[i].load;
        assert(a>(x>y?x:y)+50);
        loads[t[i].core]=x;loads[t[i].new_core]=y;
      }
    }
    unsigned peak=0;for(unsigned c=0;c<cores;c++)if(loads[c]>peak)peak=loads[c];assert(after==peak);
  }
  puts("PASS ASan/UBSan: 20000 placements; one move, fixed affinity, urgent fallback, pair gain and projected loads");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-balance-') as tmp:
        p, exe = Path(tmp)/'test.c', Path(tmp)/'test'
        p.write_text(code)
        subprocess.run(['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();native(args.source)
    workers=[(11+i,1<<core,load,0) for i,(load,core) in enumerate(CASE)]
    old=Model(args.before);old.balance(workers);assert len(old.sets)==7
    new=Model(args.elf);new.balance(workers)
    assert new.read32(new.symbols['wine_nx_fex_balance_stable'])==1
    assert new.sets==[(16,2,4)] and len(new.follow)==1 and new.read32(new.pipe+96)==4
    # Same binary control reproduces checkpoint's full placement/syscall list.
    control=Model(args.elf);control.u32(control.symbols['wine_nx_fex_balance_stable'],0)
    control.balance(workers);assert control.sets==old.sets
    # Repeated steady sampling converges, never moving two threads per pass.
    placements=[]
    for _ in range(12):
        n=len(new.sets);new.now+=100000
        for handle,_,load,_ in workers:new.ticks[handle]+=load*100
        new.call('wine_nx_thread_balance');assert len(new.sets)-n<=1
        placements.append(dict(new.masks))
    assert placements[-1]==placements[-2]==placements[-3]
    secondary=[(11,1,1000,1),(22,2,400,0),(33,2,300,0),(44,4,100,0)]
    new=Model(args.elf);new.balance(secondary);assert new.sets==[(33,2,4)]
    new=Model(args.elf);new.set_error=0xdead;new.balance(workers)
    assert len(new.sets)==1 and not new.follow and new.read32(new.pipe+96)==0
    new=Model(args.elf);new.u32(new.symbols['wine_nx_balance_enabled'],0);new.balance(workers)
    assert not new.sets
    new=Model(args.elf);new.balance([(h,m,l,1) for h,m,l,_ in workers]);assert not new.sets
    # Yield function has been restored byte-for-byte at source level.
    old_patches=json.loads((ROOT/'local/fex3/yield-burst/runtime/wine-patches.json').read_text())
    sync=args.source/'dlls/ntdll/unix/sync.c'
    sync_text, _ = undo_polling(sync.read_text(), ROOT, 'dlls/ntdll/unix/sync.c')
    if 'static NTSTATUS WINAPI fex_short_NtWaitForAlertByThreadId' in sync_text:
        # Remove only the new wrappers, then require exact original-file hash.
        # The original wait/alert bodies (including timeout policy) stay intact.
        for name in ('NtAlertThreadByThreadId','NtWaitForAlertByThreadId'):
            start=sync_text.index('\nextern '+('void wine_nx_fex_short_alert' if name=='NtAlertThreadByThreadId' else 'uint64_t wine_nx_fex_short_wait_begin'))
            public=function(sync_text.replace('NTSTATUS WINAPI '+name+'(', 'static NTSTATUS WINAPI '+name+'('),name).removeprefix('static ')
            end=sync_text.index(public,start)+len(public)+1
            assert sync_text[end-1]=='\n'
            assert sync_text[start-1]=="\n"
            sync_text=sync_text[:start-1]+sync_text[end:]
            sync_text=sync_text.replace('static NTSTATUS WINAPI fex_short_'+name+'(', 'NTSTATUS WINAPI '+name+'(',1)
    assert hashlib.sha256(sync_text.encode()).hexdigest()==old_patches['native-source']['dlls/ntdll/unix/sync.c']
    sources=['tests/fex_balance_stable.py','tests/fextendo_source_normalization.py','tools/fex_polling_patches.py','tests/fex_worker_cores.py','tests/fex_reservations.py',
             'tests/fex_resume_gate.py','src/runtime/fex_balance_stable.h','tools/fex_balance_stable_patches.py']
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
            'checks':['20000 sanitizer-checked policy cases: single move, eligibility, fixed affinity and projected loads',
                      'Linked ARM64 baseline makes 7 moves; candidate makes 1 and publishes server mask',
                      'Steady load converges; secondary core relieved despite dominant fixed thread',
                      'Control reproduces old moves; failed placement publishes nothing; disabled/fixed stay untouched',
                      'Generated sync.c matches yield-burst after removing only diagnostic wrappers; original bodies unchanged'],
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
            'generated_source_hashes':{p:hashlib.sha256((args.source/p).read_bytes()).hexdigest() for p in
                 ['dlls/ntdll/unix/sync.c','wine-nx-probe/source/thread_profile.c','wine-nx-probe/source/runtime.c']}}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
