/* LGPL-2.1-or-later. Defer only known routine lines to the existing flusher.
 * Unknown FEX messages, fault/error messages and flusher failure keep the
 * old immediate-flush policy. fwrite can still flush a full stdio buffer. */
static uint64_t fex_warm_deferred;
static int fex_warm_routine_line(const char *line)
{
    static const char *const prefixes[] = {
        "[FEX3-SMC2] blocks=", "[FEX-JIT] slot=",
        "[FEX2] thread create\n", "[FEX2] thread ready\n",
        "[FEX3-RESUME] waits="
    };
    unsigned i;
    for (i = 0; i < sizeof(prefixes) / sizeof(prefixes[0]); ++i)
        if (!strncmp(line, prefixes[i], strlen(prefixes[i]))) return 1;
    return 0;
}
