"""WSL: PERF23 math/balancing, bounded profiling and frame diagnostics."""
from pathlib import Path
import json,os,subprocess,tempfile
from perf17_patches import once
p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
work=p/'local/perf24'; work.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='perf24-tests-',dir=root) as tmp:
    for test in ('metrics','frames'):
        exe=Path(tmp)/test
        subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-pthread',str(p/f'tests/perf24_{test}.c'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)

path=p/'tools/build-perf23.py'
text=path.read_text().replace('local/perf23','local/perf24')
text=text.replace("work=p/'local/perf23'","work=p/'local/perf24'")
text=text.replace('runtime-perf23-transitions','runtime-perf24-diagnostics')
text=text.replace('pes13-nx-0.2.0-perf23-transitions','pes13-nx-0.2.0-perf24-diagnostics')
text=text.replace('PES13-NX PERF23','PES13-NX PERF24')
text=text.replace('perf23-baseline-check','perf24-baseline-check')
# Alias the adapter only; the preceding host tests still use PERF23 fixtures.
text=text.replace('import perf23_patches','import perf24_patches as perf23_patches')
text=once(text,"exec(compile(text,str(driver),'exec'),", 
    "text=once(text,'    return text','    return perf23_patches.adapt_recipe(text)')\n"
    "exec(compile(text,str(driver),'exec'),")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((work/'verification.json').read_text())
report.update({'diagnostics':'successful-present gaps, host-present duration, 2s/10s CPU sampling at 20ms',
               'math_emitters_identical_to_perf23':True,'hardware_tested':False})
(work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF24 diagnostics built with retained PERF23 math and SAFEFLAGS=2',flush=True)
