/* Real capture hook/queue plus OSK state machine; only libnx events modeled. */
#include <stdbool.h>
#define FX_TEST_OSK_MAIN fx_osk_regression_main
#include "fextendo_osk.c"
#undef FX_TEST_OSK_MAIN
typedef struct {int registered;} AppletHookCookie;
typedef enum {AppletHookType_OnFocusState,AppletHookType_OnCaptureButtonShortPressed=5} AppletHookType;
static void (*capture_callback)(AppletHookType,void *);
static unsigned hooks,unhooks,redirects,restores;
static int capture_fail;
static void appletHook(AppletHookCookie *cookie,void (*fn)(AppletHookType,void *),void *arg){
    assert(!arg&&!cookie->registered&&!capture_callback);cookie->registered=1;capture_callback=fn;hooks++;
}
static void appletUnhook(AppletHookCookie *cookie){assert(cookie->registered);cookie->registered=0;capture_callback=NULL;unhooks++;}
static Result appletSetRequiresCaptureButtonShortPressedMessage(bool enabled){
    if(enabled){redirects++;return capture_fail?0x1272:0;}restores++;return 0;
}
#include "../src/runtime/fextendo_keyboard_capture.h"
static void event(void){assert(capture_callback);capture_callback(AppletHookType_OnCaptureButtonShortPressed,NULL);}
int main(void){
    fresh();
    for(int s=0;s<FX_KEYBOARD_CAPTURE;s++){
        fx_keyboard_options.shortcut=s;fx_keyboard_capture_start();assert(!hooks&&!redirects);
    }
    fx_keyboard_options.shortcut=FX_KEYBOARD_CAPTURE;fx_keyboard_options.hold_ms=2000;
    capture_fail=1;fx_keyboard_capture_start();assert(hooks==1&&unhooks==1&&!fx_keyboard_capture_enabled&&!capture_callback&&!restores);
    capture_fail=0;fx_keyboard_capture_start();fx_keyboard_capture_start();
    assert(hooks==2&&redirects==2&&fx_keyboard_capture_enabled&&capture_callback);
    capture_callback(AppletHookType_OnFocusState,NULL);fx_keyboard_capture_poll();assert(!fx_keyboard_manual_pending);
    /* System event has no controller ID. P2 holding controls must not block
     * a Capture request or turn it into P2 keyboard ownership. */
    fx_samples[1].buttons=FX_PAD_A;
    event();event();fx_keyboard_capture_poll();
    assert(fx_keyboard_manual_pending&&fx_keyboard_manual_player==0&&fx_keyboard_manual_deadline==ticks+1000);
    uint64_t deadline=fx_keyboard_manual_deadline;event();ticks++;fx_keyboard_capture_poll();assert(fx_keyboard_manual_deadline==deadline);
    fx_osk_service();assert(fx_osk_blocked()&&display_open&&fx_osk_player==0); /* no 2-second hold */
    event();fx_keyboard_capture_poll();assert(!fx_keyboard_manual_pending); /* no second keyboard */
    close_keyboard();assert(!fx_osk_blocked());
    for(int reason=0;reason<5;reason++){
        if(reason==0)focus_state=0;
        if(reason==1)game_paused=1;
        if(reason==2)fx_game_active=0;
        if(reason==3)fx_keyboard_ready=0;
        if(reason==4)fx_keyboard_delivery=1;
        event();fx_keyboard_capture_poll();assert(!fx_keyboard_manual_pending&&!fx_keyboard_capture_pending);
        focus_state=1;game_paused=0;fx_game_active=fx_keyboard_ready=1;fx_keyboard_delivery=0;
    }
    event();fx_keyboard_capture_stop();assert(!fx_keyboard_capture_pending&&!capture_callback&&restores==1&&unhooks==2);
    fx_keyboard_capture_stop();assert(restores==1&&unhooks==2);
    fx_keyboard_options.shortcut=FX_KEYBOARD_DISABLED;fx_keyboard_capture_start();assert(hooks==2);
    puts("PASS: Capture opt-in, hook lifetime, failed enable cleanup, instant either-controller event, P1 ownership, busy/focus/reconnect guards and screenshot restoration");
    return 0;
}
