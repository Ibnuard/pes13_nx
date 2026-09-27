/* LGPL-2.1-or-later. Called on the log thread at one-second cadence. */
static int fex_hang_due(struct pes13_fex_stall_gate *gate,
                        uint32_t presents, uint32_t seconds)
{
    if (presents != gate->presents) {
        gate->presents = presents;
        gate->last_progress = seconds;
        return 0;
    }
    if (presents < 100 || seconds - gate->last_progress < 3 || gate->captures >= 3 ||
        (gate->captures && seconds - gate->last_capture < 5)) return 0;
    gate->last_capture = seconds;
    ++gate->captures;
    return 1;
}
