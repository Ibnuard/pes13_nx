"""Run the launcher checks and linked runtime regressions on one final ELF."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--python',required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--module',type=Path,default=ROOT/'local/fex3/emit-vsync/module/libwow64fex.dll');p.add_argument('--work',type=Path,default=ROOT/'local/fex3/fextendo');a=p.parse_args();w=a.work.resolve();s=a.source.resolve()
    elf=w/'runtime/reference/pes13-fex.elf'
    specs=[('cores','fex_worker_cores.py','sleep-deadline'),('launcher','fextendo_launcher.py',None),
           ('gap','fex_gap_probe.py',None),('balance','fex_balance_stable.py','yield-burst'),
           ('yield','fex_yield_burst.py','camera-720'),('resume','fex_resume_binary.py',None),
           ('pipeline','fex_pipeline_binary.py',None),('jit-log','fex_jit_log_queue.py','worker-cores'),
           ('unwind','fex_unwind.py',None)]
    receipt=json.loads((w/'runtime/runtime-build.json').read_text())
    if receipt.get('memory_audit'):specs.append(('memory','fex_memory_probe.py',None))
    if receipt.get('memory_budget_filter'):specs.append(('budget','fex_memory_budget.py',None))
    def run(spec):
        name,script,before=spec;cmd=[a.python,'-B',str(ROOT/'tests'/script)]
        if name=='launcher':cmd+=['--work',str(w),'--source',str(s)]
        elif name=='unwind':cmd+=list(map(str,[w/'runtime/payload/ntdll.dll',a.module,w/'runtime/payload/wow64.dll']))+['--elf',str(elf)]
        else:
            cmd+=[str(elf)]
            if before:cmd+=['--before',str(ROOT/f'local/fex3/{before}/runtime/reference/pes13-fex.elf')]
            if name in ('cores','gap','balance','yield','jit-log','memory','budget'):cmd+=['--source',str(s)]
        if name!='launcher':cmd+=['--output',str(w/(name+'.json'))]
        with (w/(name+'-test.txt')).open('w') as f:
            result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=900)
        if result.returncode:raise RuntimeError(name+' failed: '+str(w/(name+'-test.txt')))
        return name
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,spec) for spec in specs]):print(future.result()+': PASS',flush=True)

if __name__=='__main__':main()
