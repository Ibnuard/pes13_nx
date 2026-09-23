"""Version the existing scoped-environment machinery on the PERF25 behavior."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]
text=(p/'src/runtime/pes13_perf29.h').read_text().replace('29','32')
text=text.replace('Measured','Game').replace('measured','game')
text=text.replace('dynarec_bigblock=1','dynarec_bigblock=3').replace('scoped_BIGBLOCK=1','scoped_BIGBLOCK=3')
text=text.replace('[PERF32] worker_blocks=', '[PERF32] base=PERF25 CALLRET=0 worker_blocks=')
(p/'src/runtime/pes13_perf32.h').write_text(text)
test=(p/'tests/perf29_policy.c').read_text().replace('29','32')
test=test.replace('#include "../src/runtime/pes13_perf26.h"\n','')
test=test.replace('#include "../local/perf26/pes13_perf21_callret.h"','#include "../src/runtime/pes13_perf21.h"')
test=test.replace('pes26_mode=1;','').replace('base->dynarec_callret==2','base->dynarec_callret==0')
start=test.index('    const uintptr_t excluded[]=')
end=test.index('    for(unsigned i=0;',start)
test=test[:start]+'''    const uintptr_t excluded[]={0,0x400fff,0x112f000,0x112fb90,0x112ffff,
        0x1150000,0x115c36f,0x116ffff,0x13d1000,0xfa390000,UINTPTR_MAX};
'''+test[end:]
test=test.replace('expected.dynarec_bigblock=1','expected.dynarec_bigblock=3')
test=test.replace('const uintptr_t ranges[][2]={{0x920000,0x950000},{0x1100000,0x112f000},\n        {0x1130000,0x1150000},{0x1170000,0x11b0000}};',
    'const uintptr_t ranges[][2]={{0x401000,0x112f000},{0x1130000,0x1150000},{0x1170000,0x13d1000}};')
test=test.replace('r<4;++r','r<3;++r')
(p/'tests/perf32_policy.c').write_text(test)
test=(p/'tests/perf29_policy.py').read_text().replace('29','32')
test=test.replace('from perf26_patches import policy_text\n','')
test=test.replace("assert (p/'local/perf26/pes13_perf21_callret.h').read_text()==policy_text(p)\n",'')
(p/'tests/perf32_policy.py').write_text(test)
driver=(p/'tools/run-perf31-build.py').read_text().replace('31','32')
(p/'tools/run-perf32-build.py').write_text(driver)
