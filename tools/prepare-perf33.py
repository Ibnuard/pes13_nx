"""Validate the checked-in PERF33 fastmath policy without rewriting it."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parents[1]
required=[p/"src/runtime/pes13_perf33.h",p/"src/runtime/pes13_perf33_policy.h",p/"tools/perf33_patches.py"]
assert all(f.exists() for f in required)
text=(p/"src/runtime/pes13_perf33.h").read_text()
for marker in ("dynarec_fastnan=1","dynarec_strongmem=0","dynarec_forward=1024","dynarec_bigblock=3"):
    assert marker in text,marker
report={"policy":"PERF33 fastmath","hardware_tested":False,"files":{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in required}}
(p/"local/perf33").mkdir(parents=True,exist_ok=True)
(p/"local/perf33/prepare.json").write_text(json.dumps(report,indent=2)+"\n")
print("PERF33 policy preflight PASS")
