/* PES13 input defaults and bounded diagnostics. LGPL-2.1-or-later. */
#ifndef PES13_CONTROLLER_H
#define PES13_CONTROLLER_H
#include <stdint.h>

/* Same order as WINE_NX_KEY_* in runtime.c. Face buttons follow physical
 * positions, like the native XInput path: bottom B = Xbox A = short pass.
 * Minus provides Enter in keyboard mode for menus; Plus remains Escape. */
#define PES13_KEY_DEFAULTS { \
    0x26, 0x28, 0x25, 0x27, /* arrows */ \
    0x57, 0x41,             /* X: W through pass; Y: A shoot */ \
    0x51, 0x45,             /* L: Q cursor; R: E dash */ \
    0x5a, 0x43,             /* ZL: Z manual; ZR: C special */ \
    0x1b, 0x0d,             /* Plus: Escape; Minus: Enter */ \
    0, 0,                  /* stick presses: no keyboard modifier */ \
    0x44, 0x58              /* A: D long pass; B: X short pass */ \
}

#define PES13_INPUT_TRACE_LIMIT 128u
#define PES13_INPUT_TRACE_SOURCES 3u
struct pes13_input_trace_state
{
    uint64_t raw;
    unsigned int value, mode, count;
};

/* Call under the trace lock. Axes are deliberately excluded: stick jitter
 * must not consume the log budget or generate a per-frame SD write. */
static inline int pes13_input_trace_changed(struct pes13_input_trace_state *state,
                                           uint64_t raw, unsigned int value, unsigned int mode)
{
    if (state->count >= PES13_INPUT_TRACE_LIMIT) return 0;
    if (state->count && state->raw == raw && state->value == value && state->mode == mode) return 0;
    state->raw = raw;
    state->value = value;
    state->mode = mode;
    ++state->count;
    return 1;
}

static inline int pes13_input_uses_xinput(uint64_t now, uint64_t last_poll,
                                        uint64_t ticks_per_second, int keyboard_only,
                                        int gamepad_only)
{
    return !keyboard_only && (gamepad_only ||
           (last_poll && (last_poll >= now || now - last_poll < ticks_per_second)));
}
#endif
