/* Exact-block FPCR hoisting. Runs under the translator lock before the
 * existing cache flush, publication, or executable-alias conversion.
 * Branches preserve every native offset used by signal/profiler metadata. */
static int pes19_mode;
static unsigned int pes19_seen, pes19_applied, pes19_rejected;
static uint64_t pes19_last_guest, pes19_last_native;
static size_t pes19_last_size;

static uint64_t pes19_hash(const void *data, size_t size)
{
    const unsigned char *p = data;
    uint64_t h = UINT64_C(0xcbf29ce484222325);
    size_t i;
    for (i=0; i<size; ++i) h = (h ^ p[i]) * UINT64_C(0x100000001b3);
    return h;
}

void wine_nx_perf19_patch(void *opaque)
{
    dynablock_t *db = opaque;
    uint32_t *code;
    unsigned int i, nset=0, nrestore=0, sets[143], restores[143];
    if (!pes19_mode || !pes17_check_image() || !db->is32bits ||
        (uintptr_t)db->x64_addr != 0x112fb90) return;
    __atomic_add_fetch(&pes19_seen, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&pes19_last_size, db->native_size, __ATOMIC_RELAXED);
    if (db->x64_size != 656 || db->native_size != 7064 || db->sep_size || db->callret_size)
        goto reject;
    code = db->block; /* still the writable alias */
    uint64_t guest = pes19_hash((const void *)db->x64_readaddr, db->x64_size);
    uint64_t native = pes19_hash(code, db->native_size);
    __atomic_store_n(&pes19_last_guest, guest, __ATOMIC_RELAXED);
    __atomic_store_n(&pes19_last_native, native, __ATOMIC_RELAXED);
    if (guest != UINT64_C(0x56a853c69521644f) || native != UINT64_C(0xe1beef3eed598251))
        goto reject;
    for (i=0; i<7064/4; ++i) {
        if (code[i] == 0xb9431c01) { if (nset == 143) goto reject; sets[nset++] = i; }
        if (code[i] == 0xd51b4404) { if (nrestore == 143) goto reject; restores[nrestore++] = i; }
    }
    if (nset != 143 || nrestore != 143) goto reject;
    /* All validation completes before the first write. No partial changes. */
    for (i=1; i<143; ++i) code[sets[i]] = 0x14000008;
    for (i=0; i<142; ++i)
        code[restores[i]] = restores[i]+1 == sets[i+1] ? 0x14000009 : 0xd503201f;
    __atomic_add_fetch(&pes19_applied, 1, __ATOMIC_RELAXED);
    return;
reject:
    __atomic_add_fetch(&pes19_rejected, 1, __ATOMIC_RELAXED);
}

void wine_nx_perf19_report(void)
{
    char line[300];
    snprintf(line, sizeof(line),
        "[PERF19] matrix=%d identity=%d seen=%u applied=%u rejected=%u native_bytes=%lu guest_hash=%016llx native_hash=%016llx",
        __atomic_load_n(&pes19_mode, __ATOMIC_ACQUIRE),
        __atomic_load_n(&pes17_identity, __ATOMIC_ACQUIRE),
        __atomic_load_n(&pes19_seen, __ATOMIC_RELAXED),
        __atomic_load_n(&pes19_applied, __ATOMIC_RELAXED),
        __atomic_load_n(&pes19_rejected, __ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&pes19_last_size, __ATOMIC_RELAXED),
        (unsigned long long)__atomic_load_n(&pes19_last_guest, __ATOMIC_RELAXED),
        (unsigned long long)__atomic_load_n(&pes19_last_native, __ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
