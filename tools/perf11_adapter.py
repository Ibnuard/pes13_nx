"""Adapt the PES x86-only Horizon integration to upstream Box64 v0.4.4.

The vendor tree stays clean. Edits apply to the generated-source recipe and
the local adapter, retaining the PES runtime's settings and execution boundary.
"""
REVISION = '2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a'

def replace(text, old, new):
    assert old in text, old
    return text.replace(old, new)

def adapt(cmake, dynarec, engine):
    cmake = replace(cmake, 'dae0917c47b4edd8956f314210417a20fd225c4b', REVISION)
    cmake = cmake.replace('Box64 v0.4.0', 'Box64 v0.4.4')
    cmake = replace(cmake, '    list(TRANSFORM sources PREPEND "${root}/src/emu/")',
                     '    list(TRANSFORM sources PREPEND "${root}/src/emu/")\n    list(APPEND sources "${root}/src/tools/bitutils.c")')
    # v0.4.4 already flushes dirty CALLRET marks and removed the db_new site.
    for label in ('flush callret marks of dirty blocks', 'callret site writes on switch'):
        # Locate the immediately preceding patch command, not earlier patches.
        end = cmake.index('"' + label + '")') + len(label) + 3
        start = cmake.rfind('    wine_nx_box64_patch(', 0, end)
        cmake = cmake[:start] + cmake[end:].lstrip('\n')
    cmake = replace(cmake,
        '(skip)?NULL:DBGetBlock(emu, R_RIP, 1, is32bits)',
        '(skip || ACCESS_FLAG(F_TF))?NULL:fastDBGetBlock(emu, R_RIP, 1, is32bits)')
    cmake = replace(cmake, '3*sizeof(void*)', 'JMPNEXT_SIZE-sizeof(void*)')
    cmake = replace(cmake,
        '    //block->x64_addr = (void*)start;\\n    block->x64_size = end-start;',
        '            //block->x64_addr = (void*)start;\\n            block->x64_size = end-start;')
    for old, new in (
        ('default, min, max, wine)', 'default, min, max, wine, dynacache)'),
        ('default, wine)', 'default, wine, dynacache)'),
        ('name, wine)', 'name, wine, dynacache)'),
    ):
        dynarec = replace(dynarec, old, new)
    dynarec = replace(dynarec, '    box64env.dynarec = 1;',
                      '    box64env.dynacache = 0; /* No Linux disk-cache integration on Horizon. */\n    box64env.dynarec = 1;')
    start = dynarec.index('dynablock_t *getDB( uintptr_t addr )')
    end = dynarec.index('void *customMalloc(', start)
    dynarec = dynarec[:start] + '''/* v0.4.4 adapter contract: publish both block and exact entry target. */
dynablock_t *getDBBlock( uintptr_t addr, void **jblock )
{
    uintptr_t target = getJumpAddress64( addr );
    if (jblock) *jblock = (void *)target;
    return *(dynablock_t **)(target - sizeof(void *));
}
dynablock_t *getDB( uintptr_t addr ) { return getDBBlock( addr, NULL ); }
int getNeedTest( uintptr_t addr )
{
    void *target;
    dynablock_t *block = getDBBlock( addr, &target );
    if (!block || target != block->jmpnext) return 0;
    __atomic_add_fetch( &wine_nx_box64_marked_lookups, 1, __ATOMIC_RELAXED );
    return 1;
}
dynablock_t *getDBnoTest( uintptr_t addr )
{
    void *target;
    dynablock_t *block = getDBBlock( addr, &target );
    return block && target != block->jmpnext ? block : NULL;
}

''' + dynarec[end:]
    dynarec = replace(dynarec,
        'const char *GetNativeName( void *ptr ) { (void)ptr; return NULL; }',
        'const char *GetNativeName( void *ptr, int lib ) { (void)ptr; (void)lib; return NULL; }')
    engine = replace(engine, 'void my_cpuid( x64emu_t *emu, uint32_t leaf )\n{',
                     'void my_cpuid( x64emu_t *emu )\n{\n    uint32_t leaf = emu->regs[_AX].dword[0];')
    engine += '''
/* Upstream Horizon adapter contract: no Linux alternate-function wrappers. */
int box64_is32bits = 1;
uintptr_t getAlternateJump( void *address, int is32bits )
{ (void)address; (void)is32bits; return 0; }
void *getAlternateData( void *address ) { (void)address; return (void *)-1LL; }
void setAlternateData( void *address, void *data ) { (void)address; (void)data; }
'''
    return cmake, dynarec, engine
