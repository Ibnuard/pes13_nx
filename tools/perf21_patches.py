"""Make the pinned ARM64 emitters honor FASTROUND per-block, not globally."""
from pathlib import Path
import hashlib
import json
from perf17_patches import once

# Pin the set, so an upstream layout change cannot quietly omit an emitter.
OPS = ('0f','660f','avx_66_0f','avx_f2_0f','avx_f3_0f',
       'd8','d9','da','db','dc','de','f20f','f30f')

def generate(root, project):
    arm=root/'runtime-perf11-source/wine-nx-probe/vendor/box64/src/dynarec/arm64'
    out=project/'local/perf21/generated'
    out.mkdir(parents=True, exist_ok=True)
    old='BOX64ENV(dynarec_fastround)'
    new='BOX64DRENV(dynarec_fastround)'
    found={p.name for p in arm.glob('*.c') if old in p.read_text()}
    assert found == {f'dynarec_arm64_{op}.c' for op in OPS}, found
    result=[]
    for name in sorted(found):
        original=(arm/name).read_text()
        changed=original.replace(old,new)
        assert changed.replace(new,old)==original and old not in changed
        (out/name).write_text(changed)
        result.append({'name':name,'sites':original.count(old),
                       'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
                       'generated_sha256':hashlib.sha256(changed.encode()).hexdigest()})
    (project/'local/perf21/emitter-changes.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def adapt_cmake(cmake, project):
    hook='    list(TRANSFORM pass_sources PREPEND "${root}/src/dynarec/arm64/")'
    extra=''
    for op in OPS:
        name=f'dynarec_arm64_{op}.c'
        extra+='\n    list(REMOVE_ITEM pass_sources "${root}/src/dynarec/arm64/'+name+'")'
        extra+='\n    list(APPEND pass_sources "'+str(project/'local/perf21/generated'/name)+'")'
    return once(cmake,hook,hook+extra)
