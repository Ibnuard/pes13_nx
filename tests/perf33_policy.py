"""WSL policy/integration tests. These do not establish game speed/correctness."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
p=Path(__file__).resolve().parents[1];w=p/'local/perf33';w.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(p/'tools'))
from perf33_patches import copy_header
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source/wine-nx-probe'
(w/'pes13_perf25_env.h').write_text(copy_header(p))
with tempfile.TemporaryDirectory(prefix='perf33-policy-',dir=root) as tmp:
    exe=Path(tmp)/'policy'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(source/'vendor/box64/src/include'),'-I'+str(source/'vendor/box64/src'),
        str(p/'tests/perf33_policy.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(p/'local/game/pes2013.exe')],check=True)
files=['tests/perf33_policy.c','tests/perf33_policy.py','tools/perf33_patches.py',
    'src/runtime/pes13_perf33.h','src/runtime/pes13_perf33_policy.h']
report={'asan_ubsan':'PASS','actual_pinned_environment_struct':True,'fastmath_policy_changed':True,
    'four_pass_stability_copy_and_fault_capture':'PASS','hardware_tested':False,
    'limits':['Does not execute a complete generated guest block or a Switch game.'],
    'source_sha256':{f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in files}}
(w/'policy-tests.json').write_text(json.dumps(report,indent=2)+'\n')
