/* Include inside the Box64 bridge after its arena/block-map declarations.
 * Reuses the profiler's existing lock-free map. Arena aliases are persistent;
 * reject unfinished blocks and padding rather than reading guest memory. */
int wine_nx_box64_sample_detail(uintptr_t pc, struct pes37_sample *sample)
{
    size_t offset;
    struct nx_arena *arena;
    dynablock_t *db;
    uintptr_t native, start, within;
    memset(sample,0,sizeof(*sample));
    if ((pc&3) || !(arena=find_arena((void *)pc,&offset)) || !arena->rw ||
        offset>arena->used || arena->used-offset<sizeof(uint32_t) ||
        !(db=block_at(arena,offset)) || !db->done) return 0;
    native=(uintptr_t)arena->rx+offset;
    start=(uintptr_t)db->block;
    if (native<start) return 0;
    within=native-start;
    if (within>db->native_size || db->native_size-within<sizeof(uint32_t) ||
        db->native_size>UINT32_MAX || db->x64_size>UINT32_MAX) return 0;
    sample->guest_pc=getX64Address(db,native);
    sample->block=(uintptr_t)db->x64_addr;
    sample->guest_bytes=(uint32_t)db->x64_size;
    sample->arm_bytes=(uint32_t)db->native_size;
    memcpy(&sample->word,arena->rw+offset,sizeof(sample->word));
    sample->valid=1;
    return 1;
}
