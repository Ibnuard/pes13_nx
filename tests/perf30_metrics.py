from pathlib import Path
import hashlib,json,os,subprocess,tempfile
p=Path(__file__).resolve().parents[1];w=p/'local/perf30';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
with tempfile.TemporaryDirectory(prefix='perf30-metrics-',dir=root) as tmp:
    exe=Path(tmp)/'metrics'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined',
        str(p/'tests/perf30_metrics.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
files=['src/runtime/pes13_perf30.h','src/runtime/pes13_perf30_core.h','tests/perf30_metrics.c','tests/perf30_metrics.py']
(w/'metrics-tests.json').write_text(json.dumps({'asan_ubsan':'PASS','concurrent_nested_pairs':80000,
    'hardware_tested':False,'source_sha256':{f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in files}},indent=2)+'\n')
