"""Generate per-block FASTROUND + X87DOUBLE reads for the pinned translator."""
from pathlib import Path
import hashlib, json
from perf17_patches import once
from perf21_patches import OPS

def generate(root, project):
    source=root/'runtime-perf11-source/wine-nx-probe/vendor/box64/src/dynarec'
    arm=source/'arm64'; out=project/'local/perf22/generated'
    out.mkdir(parents=True,exist_ok=True)
    keys=('dynarec_fastround','dynarec_x87double')
    found={p.name for p in arm.glob('*.c') if any('BOX64ENV('+k+')' in p.read_text() for k in keys)}
    assert found=={f'dynarec_arm64_{op}.c' for op in OPS},found
    result=[]
    for name in sorted(found):
        original=(arm/name).read_text(); changed=original; counts={}
        for key in keys:
            old=f'BOX64ENV({key})'; new=f'BOX64DRENV({key})'
            counts[key]=original.count(old)
            changed=changed.replace(old,new)
        reverse=changed
        for key in keys: reverse=reverse.replace(f'BOX64DRENV({key})',f'BOX64ENV({key})')
        assert reverse==original
        assert counts['dynarec_x87double']==int(name=='dynarec_arm64_d9.c')
        (out/name).write_text(changed)
        result.append({'name':name,'sites':sum(counts.values()),'counts':counts,
            'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'generated_sha256':hashlib.sha256(changed.encode()).hexdigest()})
    assert sum(e['counts']['dynarec_fastround'] for e in result)==146
    assert (source/'dynarec_native.c').read_text().count('BOX64ENV(dynarec_x87double)')==2
    (project/'local/perf22/emitter-changes.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def adapt_cmake(cmake, project):
    from perf21_patches import adapt_cmake as previous
    cmake=previous(cmake,project).replace('local/perf21/generated','local/perf22/generated')
    anchor='    set(native_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_native.c")'
    patch='''    string(REPLACE "BOX64ENV(dynarec_x87double)" "BOX64DRENV(dynarec_x87double)" native_source "${native_source}")
'''
    return once(cmake,anchor,patch+anchor)
