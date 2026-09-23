"""Host-test the actual v0.4.4 Horizon jump-entry helper implementation."""
from pathlib import Path
import subprocess
import sys
import tempfile

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project/'tools'))
from perf11_adapter import adapt
source = Path(sys.argv[1])/'wine-nx-probe'
# Adapt clean baseline text after removing PERF8's diagnostic patch blocks via
# the build's own generated adapter snapshot passed as an optional argument.
text = Path(sys.argv[2]).read_text() if len(sys.argv)>2 else (source/'source/wow64_box64_dynarec.c').read_text()
start = text.index('dynablock_t *getDBBlock(')
end = text.index('void *customMalloc(', start)
code = text[start:end]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
typedef struct { void *block; void *jmpnext; } dynablock_t;
typedef struct { dynablock_t *owner; uintptr_t instruction; } entry_t;
static uintptr_t current;
static unsigned int wine_nx_box64_marked_lookups;
static uintptr_t getJumpAddress64(uintptr_t addr) { (void)addr; return current; }
'''
main = r'''
int main(void) {
    entry_t empty={0}, clean={0}, dirty={0}, secondary={0};
    dynablock_t block={&clean.instruction, &dirty.instruction};
    void *target;
    clean.owner=dirty.owner=secondary.owner=&block;
    current=(uintptr_t)&empty.instruction;
    assert(!getDB(0) && !getDBnoTest(0) && !getNeedTest(0));
    current=(uintptr_t)&clean.instruction;
    assert(getDBBlock(0,&target)==&block && target==block.block);
    assert(getDBnoTest(0)==&block && !getNeedTest(0));
    current=(uintptr_t)&dirty.instruction;
    assert(getDB(0)==&block && !getDBnoTest(0) && getNeedTest(0));
    current=(uintptr_t)&secondary.instruction;
    assert(getDBnoTest(0)==&block && !getNeedTest(0));
    assert(wine_nx_box64_marked_lookups==1);
    puts("PERF11 lookup: empty/clean/dirty/secondary entry PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='perf11-lookup-') as tmp:
    c=Path(tmp)/'test.c'
    binary=Path(tmp)/'test'
    c.write_text(harness+code+main)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-O2',str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
