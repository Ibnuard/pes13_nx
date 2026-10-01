"""Opt-in native software keyboard preview, on the validated controller base."""

def apply(read, replace, project, overlay=False):
    replace('wine-nx-probe/CMakeLists.txt',
            'target_include_directories(wine-nx-runtime PRIVATE "' + str(project / 'src/runtime') + '")',
            'target_include_directories(wine-nx-runtime PRIVATE "' + str(project / 'src/runtime') + '")\n'
            'target_include_directories(wine-win32u-real PRIVATE "' + str(project / 'src/runtime') + '")')
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, '#include "fextendo_gamepad.h"\nstatic pthread_once_t', '''#include "fextendo_gamepad.h"
#include "fextendo_keyboard.h"
static int fx_keyboard_ready;
static int fx_keyboard_applet_active;
static int fx_keyboard_last_blocked[2];
static uint32_t fx_keyboard_packet_offset[2];
static void fx_keyboard_poll_locked(void);
static void fx_keyboard_service(void);
static void fx_keyboard_cancel_all(void);
static pthread_once_t''')
    replace(name, '    if(!fx_pad_session_captured)__atomic_store_n',
            '    fx_keyboard_poll_locked();\n    if(!fx_pad_session_captured)__atomic_store_n')
    # A foreground library applet may hide HID state from the application.
    # Check real disconnections again after its return, not while it owns HID.
    replace(name, 'if(fx_game_active&&fx_reconnect_poll(',
            'if(fx_game_active&&!__atomic_load_n(&fx_keyboard_applet_active,__ATOMIC_ACQUIRE)&&fx_reconnect_poll(')
    replace(name, '    if(!fx_pads_paused())return;',
            '    if(!fx_pads_paused()&&!__atomic_load_n(&fx_keyboard_applet_active,__ATOMIC_ACQUIRE))return;')
    replace(name, 'while(fx_pads_paused())pthread_cond_wait(&fx_pad_cond,&fx_pad_lock);',
            'while(fx_pads_paused()||__atomic_load_n(&fx_keyboard_applet_active,__ATOMIC_ACQUIRE))pthread_cond_wait(&fx_pad_cond,&fx_pad_lock);')
    replace(name, 'if(fx_pads_paused()){pthread_mutex_unlock(&fx_pad_lock);continue;}',
            'if(fx_pads_paused()||__atomic_load_n(&fx_keyboard_applet_active,__ATOMIC_ACQUIRE)){pthread_mutex_unlock(&fx_pad_lock);continue;}')
    replace(name, '*out=fx_samples[index];pthread_mutex_unlock(&fx_pad_lock);return out->connected;', '''*out=fx_samples[index];
        int blocked=fx_keyboard_input_blocked();
        if(blocked!=fx_keyboard_last_blocked[index]){fx_keyboard_last_blocked[index]=blocked;fx_keyboard_packet_offset[index]++;}
        out->packet+=fx_keyboard_packet_offset[index];
        if(blocked){out->buttons=0;out->lx=out->ly=out->rx=out->ry=0;}
        pthread_mutex_unlock(&fx_pad_lock);return out->connected;''')
    replace(name, 'static void *fx_pads_monitor(void *unused)',
            '#include "fextendo_keyboard_switch.h"\nstatic void *fx_pads_monitor(void *unused)')
    replace(name, 'if(!fx_pads_paused()){svcSleepThread(20000000);continue;}',
            'if(!fx_pads_paused()){fx_keyboard_service();svcSleepThread(20000000);continue;}\n        fx_keyboard_cancel_all();')
    replace(name, 'fx_pad_thread_created=1;atexit(fx_pads_shutdown);return 1;',
            'fx_pad_thread_created=1;__atomic_store_n(&fx_keyboard_ready,1,__ATOMIC_RELEASE);atexit(fx_pads_shutdown);return 1;')
    replace(name, 'if (fx_pads_paused()) memset(pads, 0, sizeof(pads));',
            'if (fx_pads_paused() || fx_keyboard_input_blocked()) memset(pads, 0, sizeof(pads));')
    replace(name, 'if (!fx_pads_paused() && hidGetTouchScreenStates',
            'if (!fx_pads_paused() && !fx_keyboard_input_blocked() && hidGetTouchScreenStates')
    if overlay:
        replace('wine-nx-probe/CMakeLists.txt',
                'target_include_directories(wine-win32u-real PRIVATE "' + str(project / 'src/runtime') + '")',
                'target_include_directories(wine-win32u-real PRIVATE "' + str(project / 'src/runtime') + '")\n'
                'target_compile_definitions(wine-win32u-real PRIVATE FX_KEYBOARD_OVERLAY=1)\n'
                'target_compile_definitions(wine-nx-runtime PRIVATE FX_KEYBOARD_OVERLAY=1)')
        replace(name, '#include "fextendo_keyboard_switch.h"',
                '#include "fextendo_keyboard_switch.h"\n#include "fextendo_osk_display.h"\n#include "fextendo_osk_switch.h"')
        replace(name, 'if(!fx_pads_paused()){fx_keyboard_service();svcSleepThread(20000000);continue;}',
                'if(!fx_pads_paused()){fx_keyboard_service();fx_osk_service();svcSleepThread(20000000);continue;}')
        replace(name, '        fx_keyboard_cancel_all();',
                '        fx_keyboard_cancel_all();fx_osk_service();')
        replace(name, 'if(appletGetFocusState()!=AppletFocusState_InFocus){svcSleepThread(20000000);continue;}\n        struct fx_pad_sample p[2];',
                'if(appletGetFocusState()!=AppletFocusState_InFocus){fx_osk_abort(0);fx_osk_display_close();svcSleepThread(20000000);continue;}\n        struct fx_pad_sample p[2];')
        replace(name, '    fx_pause_close(&display);return NULL;',
                '    fx_osk_abort(0);fx_osk_display_close();fx_pause_close(&display);return NULL;')
    name = 'dlls/win32u/winnx_drv.c'
    replace(name, 'BOOL wine_nx_drv_ProcessEvents( DWORD mask )',
            '#include "fextendo_keyboard_wine.h"\n\nBOOL wine_nx_drv_ProcessEvents( DWORD mask )')
    replace(name, '    keys = wine_nx_send_keys();',
            '    keys = wine_nx_send_keys();\n    keys |= fx_wine_text_pump();')
    name = 'dlls/win32u/driver.c'
    replace(name, '            extern BOOL wine_nx_drv_ProcessEvents( DWORD );', '''            extern BOOL wine_nx_drv_ProcessEvents( DWORD );
            extern void wine_nx_drv_DestroyWindow( HWND );
            extern void wine_nx_drv_NotifyIMEStatus( HWND, UINT );
            extern BOOL wine_nx_drv_SetIMECompositionRect( HWND, RECT );''')
    replace(name, '            null_user_driver.pProcessEvents        = wine_nx_drv_ProcessEvents;', '''            null_user_driver.pProcessEvents        = wine_nx_drv_ProcessEvents;
            null_user_driver.pDestroyWindow        = wine_nx_drv_DestroyWindow;
            null_user_driver.pNotifyIMEStatus      = wine_nx_drv_NotifyIMEStatus;
            null_user_driver.pSetIMECompositionRect = wine_nx_drv_SetIMECompositionRect;''')
    # Mirror Wine's VK_PACKET semantics: the entire UTF-16 unit is carried in
    # HIWORD(lParam), including surrogate halves; no raw scancode is fabricated.
    name = 'dlls/ntdll/unix/horizon_keyboard.h'
    replace(name, '    unsigned int kf = 0, up = flags & HORIZON_KEYEVENTF_KEYUP;', '''    unsigned int kf = 0, up = flags & HORIZON_KEYEVENTF_KEYUP;

    if (!input_vkey && (flags & 0x0004 /* KEYEVENTF_UNICODE */))
    {
        event->message = up ? HORIZON_KBD_WM_KEYUP : HORIZON_KBD_WM_KEYDOWN;
        event->vkey = 0xe7; /* VK_PACKET */
        event->lparam = ((unsigned long long)scan << 16) | 1;
        event->data_flags = 0;
        return;
    }''')
    name = 'dlls/ntdll/unix/horizon.c'
    replace(name, '''        if ((raw_device = horizon_rawinput_find( horizon_rawinput_devices, horizon_rawinput_device_count,
                                                 HORIZON_RAWINPUT_USAGE_KEYBOARD )))''', '''        if (!(kbd->flags & 0x0004 /* KEYEVENTF_UNICODE */) &&
            (raw_device = horizon_rawinput_find( horizon_rawinput_devices, horizon_rawinput_device_count,
                                                 HORIZON_RAWINPUT_USAGE_KEYBOARD )))''')
