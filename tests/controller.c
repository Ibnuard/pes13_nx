/* Input regression tests: defaults, handover, log bounds and real XInput map. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "windef.h"
#include "winbase.h"
#include "xinput.h"
#include "nx_pad.h"
#include "pes13_controller.h"

int main(void)
{
    const unsigned short keys[] = PES13_KEY_DEFAULTS;
    const uint64_t buttons[] = { NX_PAD_B, NX_PAD_A, NX_PAD_Y, NX_PAD_X };
    const WORD xbox[] = { XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_B, XINPUT_GAMEPAD_X, XINPUT_GAMEPAD_Y };
    struct pes13_input_trace_state state = {0};
    XINPUT_GAMEPAD pad;
    unsigned int i;
    assert(sizeof(keys) / sizeof(keys[0]) == 16);
    assert(keys[14] == 'D' && keys[15] == 'X' && keys[4] == 'W' && keys[5] == 'A');
    assert(keys[10] == 0x1b && keys[11] == 0x0d && !keys[12] && !keys[13]);
    for (i = 0; i < 4; ++i)
    {
        nx_xinput_map(buttons[i], 0, 0, 0, 0, &pad);
        assert(pad.wButtons == xbox[i]);
        nx_xinput_map(0, 0, 0, 0, 0, &pad);
        assert(!pad.wButtons);
    }
    nx_xinput_map(NX_PAD_A | NX_PAD_B | NX_PAD_X | NX_PAD_Y | NX_PAD_ZL | NX_PAD_ZR,
                  -40000, 40000, 12000, -12000, &pad);
    assert(pad.wButtons == 0xf000 && pad.bLeftTrigger == 255 && pad.bRightTrigger == 255);
    assert(pad.sThumbLX == -32768 && pad.sThumbLY == 32767 && pad.sThumbRX == 12000 && pad.sThumbRY == -12000);
    assert(sizeof(struct nx_xinput_state_params) == 24 && sizeof(struct nx_xinput_vibration_params) == 12);
    assert(!pes13_input_uses_xinput(1000, 0, 100, 0, 0));
    assert(pes13_input_uses_xinput(1000, 950, 100, 0, 0));
    assert(!pes13_input_uses_xinput(1000, 900, 100, 0, 0));
    assert(pes13_input_uses_xinput(1000, 1001, 100, 0, 0));
    assert(!pes13_input_uses_xinput(1000, 950, 100, 1, 0));
    assert(pes13_input_uses_xinput(1000, 0, 100, 0, 1));
    assert(!pes13_input_uses_xinput(1000, 950, 100, 1, 1));
    assert(pes13_input_trace_changed(&state, 0, 0, 0));
    for (i = 0; i < 10000; ++i) assert(!pes13_input_trace_changed(&state, 0, 0, 0));
    assert(state.count == 1);
    assert(pes13_input_trace_changed(&state, 1, 1, 0));
    assert(pes13_input_trace_changed(&state, 1, 1, 1));
    for (i = state.count; i < PES13_INPUT_TRACE_LIMIT; ++i)
        assert(pes13_input_trace_changed(&state, i, i, i & 1));
    for (i = 0; i < 10000; ++i) assert(!pes13_input_trace_changed(&state, i, i, 0));
    assert(state.count == PES13_INPUT_TRACE_LIMIT);
    puts("Controller: face press/release, chords, axes, ABI, fallback handover and bounded traces passed");
    return 0;
}
