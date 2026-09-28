/* FEX3 event diagnostic: one reader on existing log thread, no guest writes.
 * At one-second cadence, bracket video-visible kickoff and replay transitions.
 * Raw object/scale are not scene labels or proven simulation progress. */
static void fex_event_report(unsigned elapsed_s)
{
    static unsigned previous_presents;
    struct fex_game_timing s;
    uint64_t begin = armGetSystemTick();
    int status = fex_game_snapshot(wine_nx_fex_timing_read, &s);
    extern unsigned int wine_nx_vk_presents __attribute__((weak));
    unsigned presents = &wine_nx_vk_presents ?
        __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED) : 0;
    unsigned present_delta = presents - previous_presents;
    if (status != 1)
        log_line("[FEX3-EVENT] elapsed_s=%u snapshot=%d presents=%u present_delta=%u read_us=%llu",
                 elapsed_s, status, presents, present_delta,
                 (unsigned long long)(armTicksToNs(armGetSystemTick() - begin) / 1000));
    else
        log_line("[FEX3-EVENT] elapsed_s=%u object=%08x state=%u mode=%u scale_bits=%08x presents=%u present_delta=%u ring_count=%u read_us=%llu",
                 elapsed_s, s.object_address, s.object[7], s.object[6], s.object[8],
                 presents, present_delta, s.pacer[0x88 / 4],
                 (unsigned long long)(armTicksToNs(armGetSystemTick() - begin) / 1000));
    previous_presents = presents;
}
