"""Durable WSL entry point: snapshot mutable sources before the build starts."""
from pathlib import Path
import hashlib,json,os,runpy,sys,traceback
p=Path(__file__).resolve().parents[1];w=p/'local/perf29';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source';sha=lambda b:hashlib.sha256(b).hexdigest()
previous=json.loads((p/'local/perf28/recovery.json').read_text())
records={}
for rel,old in previous.items():
    data=(source/rel).read_bytes()
    assert sha(data)==old['baseline'],('unexpected source edits; do not overwrite',rel)
    backup=w/'source-baseline'/rel;backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists(): assert backup.read_bytes()==data,rel
    else: backup.write_bytes(data)
    records[rel]=sha(data)
(w/'source-baseline.json').write_text(json.dumps(records,indent=2)+'\n')
(w/'build-status.json').write_text(json.dumps({'state':'running','pid':os.getpid()}))
sys.path.insert(0,str(p/'tools'))
try:
    if '--verify-only' not in sys.argv:
        runpy.run_path(str(p/'tools/build-perf29.py'),run_name='__main__')
    assert all(sha((source/rel).read_bytes())==digest for rel,digest in records.items())
    runpy.run_path(str(p/'tools/verify-perf29.py'),run_name='__main__')
    (w/'build-status.json').write_text(json.dumps({'state':'complete','restored':True}))
except BaseException:
    restored=all(sha((source/rel).read_bytes())==digest for rel,digest in records.items())
    (w/'build-status.json').write_text(json.dumps({'state':'failed','restored':restored,'error':traceback.format_exc()},indent=2))
    raise
