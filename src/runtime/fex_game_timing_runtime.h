/* Included in runtime.c before log_flusher. One reader, every five seconds.
 * No timer scaling, frame caps, game-data writes, or thread suspension. */
static int fex_game_timing_enabled;
extern int wine_nx_fex_timing_read(uint32_t address, void *out, size_t size);

static void fex_game_timing_report(void)
{
    static uint64_t previous_tick, previous_ring, previous_fixed;
    static uint32_t previous_object;
    static int previous_status = -99;
    struct fex_game_timing s;
    uint64_t begin, now, ring, fixed, host_us, ring_delta = 0, fixed_delta = 0;
    int status;
    if (!fex_game_timing_enabled) return;
    begin = armGetSystemTick();
    status = fex_game_snapshot(wine_nx_fex_timing_read, &s);
    now = armGetSystemTick();
    if (status != 1) {
        if (status != previous_status)
            log_line("[FEX3-GAME] snapshot=%d (0=unmapped,-1=unknown-image,-2=object,-3=changed); read-only", status);
        previous_tick = previous_ring = previous_fixed = 0;
        previous_status = status;
        return;
    }
    previous_status = status;
    ring = fex_game_ring_time(&s);
    fixed = fex_game_u64(s.pacer + 0xd8 / 4);
    host_us = previous_tick && now >= previous_tick ? armTicksToNs(now - previous_tick) / 1000 : 0;
    if (previous_object == s.object_address && host_us) {
        if (previous_ring && ring >= previous_ring) ring_delta = ring - previous_ring;
        if (previous_fixed && fixed >= previous_fixed) fixed_delta = fixed - previous_fixed;
    }
    log_line("[FEX3-GAME] object=%08x flags=%04x vsync=%u settings_skip=%u object_skip=%u refresh_index=%u mode=%u state=%u interval=%d scale_bits=%08x read_us=%llu",
             s.object_address, s.settings, s.settings & 1, (s.settings >> 1) & 1,
             s.object[5] & 255, s.object[1], s.object[6], s.object[7],
             (int32_t)s.object[4], s.object[8],
             (unsigned long long)(armTicksToNs(now - begin) / 1000));
    log_line("[FEX3-GCLOCK] host_delta_us=%llu ring_us=%llu ring_delta_us=%llu fixed_us=%llu fixed_delta_us=%llu ring_gap_us=%llu count=%u; last-frame timestamps, not simulation rate",
             (unsigned long long)host_us, (unsigned long long)ring, (unsigned long long)ring_delta,
             (unsigned long long)fixed, (unsigned long long)fixed_delta,
             (unsigned long long)fex_game_ring_gap(&s), s.pacer[0x88 / 4]);
    log_line("[FEX3-PACER] refresh=%u interval=%u flags=%08x fixed_hz_bits=%08x quantum_us=%u pattern_index=%u table_index=%u accumulated=%u last_step=%u display_hz=%u display_interval=%u display_rate_bits=%08x display_fixed_bits=%08x",
             s.pacer[0x90 / 4], s.pacer[0x8c / 4], s.pacer[0x94 / 4], s.pacer[0xd0 / 4],
             s.pacer[0xa0 / 4], s.pacer[0xa8 / 4], s.pacer[0xac / 4],
             s.pacer[0xb0 / 4], s.pacer[0xb4 / 4] & 255,
             s.display[2], s.display[3], s.display[4], s.display[5]);
    previous_tick = now; previous_ring = ring; previous_fixed = fixed;
    previous_object = s.object_address;
}
