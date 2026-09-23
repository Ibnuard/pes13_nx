/* Compile-time policy only. No counters, C calls or log I/O per guest op. */
static int pes18_mode;
static unsigned int pes18_sites, pes18_matrix_sites;

int wine_nx_perf18_round_site(uintptr_t addr, int pass)
{
    int matrix = addr >= 0x112fb90 && addr < 0x112fe20;
    int worker = (addr >= 0x937990 && addr < 0x9379cf) ||
                 (addr >= 0x93b83b && addr < 0x93b84d) ||
                 (addr >= 0x93cff0 && addr < 0x93d000);
    if ((!matrix && !worker) || !pes18_mode || !pes17_check_image()) return 0;
    if (pass == 3) {
        __atomic_add_fetch(&pes18_sites, 1, __ATOMIC_RELAXED);
        if (matrix) __atomic_add_fetch(&pes18_matrix_sites, 1, __ATOMIC_RELAXED);
    }
    return 1;
}

void wine_nx_perf18_report(void)
{
    char line[200];
    snprintf(line, sizeof(line),
             "[PERF18] roundguard=%d identity=%d emitted_sites=%u matrix_sites=%u",
             __atomic_load_n(&pes18_mode, __ATOMIC_ACQUIRE),
             __atomic_load_n(&pes17_identity, __ATOMIC_ACQUIRE),
             __atomic_load_n(&pes18_sites, __ATOMIC_RELAXED),
             __atomic_load_n(&pes18_matrix_sites, __ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
