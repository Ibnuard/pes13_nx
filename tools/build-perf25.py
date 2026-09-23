"""WSL: measured REP MOVSD site; preserve the established math/ABI/startup path."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
from perf17_patches import once
p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
w=p/'local/perf25';w.mkdir(parents=True,exist_ok=True)
source=root/'runtime-perf11-source/wine-nx-probe'
with tempfile.TemporaryDirectory(prefix='perf25-preflight-',dir=root) as tmp:
    exe=Path(tmp)/'policy'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(source/'vendor/box64/src/include'),'-I'+str(source/'vendor/box64/src'),
        str(p/'tests/perf25_policy.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(p/'local/game/pes2013.exe')],check=True)
env=dict(os.environ,PYTHONPATH=str(p/'local/perf20/linux-libs'))
subprocess.run([sys.executable,str(p/'tests/perf25_copy.py')],env=env,check=True)
path=p/'tools/build-perf23.py';text=path.read_text()
text=text.replace('local/perf23','local/perf25')
text=text.replace('runtime-perf23-transitions','runtime-perf25-paircopy')
text=text.replace('pes13-nx-0.2.0-perf23-transitions','pes13-nx-0.2.0-perf25-paircopy')
text=text.replace('PES13-NX PERF23','PES13-NX PERF25')
text=text.replace('perf23-baseline-check','perf25-baseline-check')
text=text.replace('import perf23_patches','import perf25_patches as perf23_patches')
# PERF22's driver checks its completion hook after the build. Only that hook
# changes; native translation logic must otherwise remain byte-identical.
injection="""text=once(text,'    return text','    return perf23_patches.adapt_recipe(text)')
text=text.replace("assert 'wine_nx_perf22_completed(block, helper.env)' in generated", "assert 'wine_nx_perf25_completed(block, helper.env)' in generated")
"""
text=once(text,"exec(compile(text,str(driver),'exec'),",injection+"exec(compile(text,str(driver),'exec'),")
text=once(text,'old[0].read_bytes()==new[0].read_bytes()',
    "old[0].read_text()==new[0].read_text().replace('wine_nx_perf25_completed','wine_nx_perf22_completed')")
text=once(text,"'native_dynarec_identical_to_perf22':True", "'native_dynarec_only_completion_hook_changed':True")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text())
report.update({'copy_tests':json.loads((w/'copy-tests.json').read_text()),
    'math_emitters_identical_to_perf24':True,'main_cpu_sampling':False,
    'startup_fix_claimed':False,'hardware_tested':False})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF25 built: scoped pair copy, math-control package required; hardware validation pending',flush=True)
