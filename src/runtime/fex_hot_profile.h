/* LGPL-2.1-or-later. FEX adaptation of Wine-NX's optional context sampler.
 * Included after fex_stall_probe.h. Uses FEX x28/frame metadata, never Box64
 * register mappings. A label is a compilation-unit entry, not an exact PC. */
static int fex_hot_pc(const ThreadContext *ctx, uintptr_t *guest)
{
    const uint64_t pc=ctx->pc.x, state=ctx->cpu_gprs[28].x;
    uint64_t block;
    uint32_t offset;
    struct pes13_fex_observed_tail tail;
    void *alias=pes13_fex_native_host()->write_alias((void *)(uintptr_t)pc,4);
    if (!alias || alias==(void *)(uintptr_t)pc || !state ||
        state>UINT64_MAX-PES13_FEX_FRAME_BLOCK_OFFSET ||
        !fex_stall_read(state+PES13_FEX_FRAME_BLOCK_OFFSET,&block,sizeof(block)) ||
        !fex_stall_read(block,&offset,sizeof(offset)) || offset>=16*1024*1024 ||
        block>UINT64_MAX-offset || !fex_stall_read(block+offset,&tail,sizeof(tail)) ||
        tail.size<offset+sizeof(tail) || tail.size>16*1024*1024 ||
        pc<block || pc-block>=tail.size || tail.rip>UINT32_MAX || !tail.rip) return 0;
    *guest=(uintptr_t)tail.rip;
    return 1;
}
