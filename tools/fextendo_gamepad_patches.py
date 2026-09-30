"""Share normalized, stable controller slots across XInput and the launcher."""

def apply(read, replace, project):
    name = 'wine-nx-probe/source/xinput_unix.c'
    replace(name, '#include <switch.h>', '#include <switch.h>\n#include "fextendo_gamepad.h"')
    src = read(name)
    start = src.index('static pthread_mutex_t pad_mutex')
    end = src.index('/* Rumble is not sent yet;', start)
    replace(name, src[start:end], '''static NTSTATUS nx_xinput_get_state_unix( void *args )
{
    struct nx_xinput_state_params *params = args;
    struct fx_pad_sample sample;
    params->connected = 0;
    memset(&params->state, 0, sizeof(params->state));
    if (wine_nx_pes13_keyboard_only || !fx_pads_game_state(params->index, &sample)) return STATUS_SUCCESS;
    nx_xinput_map(sample.buttons, sample.lx, sample.ly, sample.rx, sample.ry, &params->state.Gamepad);
    params->connected = 1;
    params->state.dwPacketNumber = sample.packet;
    __atomic_store_n(&wine_nx_xinput_last_poll, armGetSystemTick(), __ATOMIC_RELAXED);
    return STATUS_SUCCESS;
}

''')
    name = 'wine-nx-probe/source/runtime.c'
    # The legacy check configures one pad before it checks requested==0. It
    # therefore disconnects P2 even in silent production. The Gamepad tile now
    # owns testing; do not invoke or link this old console check after Play.
    replace(name, '#include "pes13_controller_ui.h"', '/* Controller diagnostics are owned by the FEXTendo Gamepad tile. */')
    replace(name, '    pes13_controller_check(wine_nx_config_file_bool(RUNTIME_DIR "/controller-test.txt", 0));',
            '    /* Preserve the launcher\'s two-controller HID configuration throughout Wine startup. */')
    replace(name, '        padConfigureInput( 1, HidNpadStyleSet_NpadStandard );\n        padInitializeDefault( &wine_nx_pad );', '        fx_pads_init();')
    replace(name, '''    padUpdate( &wine_nx_pad );
    now = armGetSystemTick();
    held = padGetButtons( &wine_nx_pad );
    stick = padGetStickPos( &wine_nx_pad, 1 );''', '''    struct fx_pad_sample pads[2];
    fx_pads_snapshot(pads);
    if (fx_pads_paused()) memset(pads, 0, sizeof(pads));
    now = armGetSystemTick();
    held = pads[0].buttons;
    stick = (HidAnalogStickState){pads[0].rx, pads[0].ry};''')
    replace(name, 'HidAnalogStickState steer = padGetStickPos( &wine_nx_pad, 0 );',
            'HidAnalogStickState steer = {pads[0].lx, pads[0].ly};')
    # The event pump must keep running while paused, but no touchscreen press may leak.
    replace(name, 'if (hidGetTouchScreenStates( &touch, 1 ) && touch.count > 0)',
            'if (!fx_pads_paused() && hidGetTouchScreenStates( &touch, 1 ) && touch.count > 0)')
    name = 'dlls/win32u/vulkan.c'
    for func in ('win32u_vkAcquireNextImage2KHR', 'win32u_vkAcquireNextImageKHR'):
        src = read(name)
        start = src.index(func + '(')
        brace = src.index('{', start)
        # Insert before the acquisition's locks and driver call.
        replace(name, src[start:brace+1], src[start:brace+1] + '\n    extern void wine_nx_gamepad_wait(void);\n    wine_nx_gamepad_wait();')
    replace('wine-nx-probe/CMakeLists.txt',
            'target_link_options(wine-nx-runtime PRIVATE -Wl,--gc-sections',
            'target_include_directories(wine-nx-runtime PRIVATE "' + str(project / 'src/runtime') + '")\n'
            'target_link_options(wine-nx-runtime PRIVATE -Wl,--gc-sections')
