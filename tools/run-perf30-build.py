"""Snapshot mutable Wine source, build and verify. Mesa is compiled from copies."""
from pathlib import Path
import hashlib,json,os,runpy,sys,traceback
p=Path(__file__).resolve().parents[1];w=p/'local/perf30';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'));source=root/'runtime-perf11-source'
os.environ['PES_BUILD_ROOT']=str(root)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
expected=json.loads((p/'local/perf29/source-baseline.json').read_text())
expected['wine-nx-probe/source/audio_unix.c']=sha(source/'wine-nx-probe/source/audio_unix.c')
records={}
for rel,digest in expected.items():
    src=source/rel;assert sha(src)==digest,('unexpected source edit',rel)
    backup=w/'source-baseline'/rel;backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists():assert backup.read_bytes()==src.read_bytes(),rel
    else:backup.write_bytes(src.read_bytes())
    records[rel]=digest
(w/'source-baseline.json').write_text(json.dumps(records,indent=2)+'\n')
(w/'build-status.json').write_text(json.dumps({'state':'running','pid':os.getpid()}))
sys.path.insert(0,str(p/'tools'))
try:
    if '--verify-only' not in sys.argv:runpy.run_path(str(p/'tools/build-perf30.py'),run_name='__main__')
    assert all(sha(source/rel)==digest for rel,digest in records.items())
    runpy.run_path(str(p/'tools/verify-perf30.py'),run_name='__main__')
    (w/'build-status.json').write_text(json.dumps({'state':'complete','restored':True}))
except BaseException:
    (w/'build-status.json').write_text(json.dumps({'state':'failed','restored':all(sha(source/rel)==d for rel,d in records.items()),
        'error':traceback.format_exc()},indent=2))
    raise
