"""Apply the bounded scratch reserve to a copy of the frozen native adapter."""
import shutil,hashlib
def apply(archive,feature,project,reserve_mib=32,pages=False):
    assert reserve_mib in (32,64)
    source=archive/'source/src/fex';dest=feature/'src/fex'
    shutil.copytree(source,dest,dirs_exist_ok=True)
    header=project/'src/fex/horizon_scratch_reserve.h'
    shutil.copy2(header,dest/header.name)
    if pages:
        for name in ('horizon_scratch_pages.h','horizon_heap_pressure.h'):
            shutil.copy2(project/'src/fex'/name,dest/name)
    else:
        for name in ('horizon_scratch_pages.h','horizon_heap_pressure.h'):
            (dest/name).unlink(missing_ok=True)
    p=dest/'horizon_jit.c';data=p.read_text()
    changes=[
      ('static void *allocate_scratch(uint64_t requested) {',
       ('#define FX_SCRATCH_UNITS 8u\n' if reserve_mib==64 else '')+('#define FX_SCRATCH_PAGES 2\n' if pages else '')+
       '#include "horizon_scratch_reserve.h"\n\nstatic void *allocate_scratch(uint64_t requested) {'),
      ('    void *result = aligned_alloc(PAGE_BYTES, size);',
       '    void *result = fx_scratch_reserve_take(size);'),
      ('static void release_scratch(void *address) { free(address); }',
       'static void release_scratch(void *address) { fx_scratch_reserve_release(address); }'),
      ('const struct pes13_fex_host *pes13_fex_native_host(void) {',
       'const struct pes13_fex_host *pes13_fex_native_host(void) {\n    fx_scratch_reserve_init();')]
    if pages:
        changes += [
          ('static void *allocate_heap(uint64_t requested, uint64_t alignment) {',
           '#include "horizon_heap_pressure.h"\n\nstatic void *allocate_heap(uint64_t requested, uint64_t alignment) {'),
          ('    void *raw = malloc((size_t)size + header_size + (size_t)alignment - 1);',
           '    const size_t raw_size = (size_t)size + header_size + (size_t)alignment - 1;\n'
           '    void *raw = malloc(raw_size);\n'
           '    if (!raw) raw = fx_private_heap_recover(raw_size, size, alignment);'),
          ('    free(header->allocation);',
           '    if (fx_scratch_reserve_return(header->allocation)) return;\n'
           '#ifdef __SWITCH__\n'
           '    if (fx_scratch_pages_release(header->allocation)) return;\n'
           '#endif\n'
           '    free(header->allocation);')]
    for old,new in changes:
        assert data.count(old)==1,old
        data=data.replace(old,new)
    p.write_text(data)
    for f in source.rglob('*'):
        if f.is_file() and f.name!='horizon_jit.c':assert f.read_bytes()==(dest/f.relative_to(source)).read_bytes()
    return dest,{str(f.relative_to(dest)):hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in sorted(dest.rglob('*')) if f.is_file()}
