/* LGPL-2.1-or-later. Included after the native controller/VI helpers.
 * The existing monitor owns ALL library applets; Wine only queues requests. */
enum fx_keyboard_phase { FX_KBD_IDLE, FX_KBD_PENDING, FX_KBD_SHOWING, FX_KBD_DRAIN, FX_KBD_DONE };
static pthread_mutex_t fx_keyboard_lock=PTHREAD_MUTEX_INITIALIZER;
static struct fx_text_request fx_keyboard_req;
static struct fx_text_result fx_keyboard_result;
static enum fx_keyboard_phase fx_keyboard_phase;
static uint64_t fx_keyboard_serial;
static int fx_keyboard_canceled,fx_keyboard_blocked,fx_keyboard_shortcut_blocked,fx_keyboard_manual_pending;
static int fx_keyboard_delivery;
static unsigned fx_keyboard_manual_player;
static uint64_t fx_keyboard_previous_buttons[2];

int fx_keyboard_input_blocked(void) {
    return
#ifdef FX_KEYBOARD_OVERLAY
        fx_osk_blocked()||
#endif
        __atomic_load_n(&fx_keyboard_blocked,__ATOMIC_ACQUIRE)||
        __atomic_load_n(&fx_keyboard_shortcut_blocked,__ATOMIC_ACQUIRE)||fx_keyboard_delivering();
}
int fx_keyboard_delivering(void){return __atomic_load_n(&fx_keyboard_delivery,__ATOMIC_ACQUIRE);}
void fx_keyboard_delivery_done(void){__atomic_store_n(&fx_keyboard_delivery,0,__ATOMIC_RELEASE);}
int fx_keyboard_manual(void) {
    return __atomic_exchange_n(&fx_keyboard_manual_pending,0,__ATOMIC_ACQ_REL);
}
unsigned fx_keyboard_manual_owner(void){return __atomic_load_n(&fx_keyboard_manual_player,__ATOMIC_ACQUIRE);}
uint64_t fx_keyboard_request(const struct fx_text_request *r) {
    uint64_t token=0;char check[FX_TEXT_BYTES];
#ifdef FX_KEYBOARD_OVERLAY
    if(fx_osk_blocked())return 0;
#endif
    if(!__atomic_load_n(&fx_keyboard_ready,__ATOMIC_ACQUIRE)||fx_pads_paused()||fx_keyboard_delivering()||!r->window||!r->thread||
       !r->limit||r->limit>FX_TEXT_UNITS||fx_text_encode(r->initial,check)<0)return 0;
    pthread_mutex_lock(&fx_keyboard_lock);
    if(fx_keyboard_phase==FX_KBD_IDLE&&!fx_keyboard_delivering()
#ifdef FX_KEYBOARD_OVERLAY
       &&!fx_osk_blocked()
#endif
    ){
        fx_keyboard_req=*r;memset(&fx_keyboard_result,0,sizeof(fx_keyboard_result));
        if(!++fx_keyboard_serial)++fx_keyboard_serial;
        token=fx_keyboard_serial;fx_keyboard_canceled=0;fx_keyboard_phase=FX_KBD_PENDING;
        __atomic_store_n(&fx_keyboard_blocked,1,__ATOMIC_RELEASE);
    }
    pthread_mutex_unlock(&fx_keyboard_lock);return token;
}
int fx_keyboard_take(uint64_t token,struct fx_text_result *result) {
    int ready=0;pthread_mutex_lock(&fx_keyboard_lock);
    if(token&&token==fx_keyboard_serial&&fx_keyboard_phase==FX_KBD_DONE){
        *result=fx_keyboard_result;ready=1;
        __atomic_store_n(&fx_keyboard_delivery,result->accepted,__ATOMIC_RELEASE);
        memset(&fx_keyboard_result,0,sizeof(fx_keyboard_result));
        memset(&fx_keyboard_req,0,sizeof(fx_keyboard_req));fx_keyboard_phase=FX_KBD_IDLE;
    }
    pthread_mutex_unlock(&fx_keyboard_lock);return ready;
}
void fx_keyboard_cancel(uint64_t token) {
    pthread_mutex_lock(&fx_keyboard_lock);
    if(token==fx_keyboard_serial){
        fx_keyboard_canceled=1;memset(&fx_keyboard_result,0,sizeof(fx_keyboard_result));
        if(fx_keyboard_phase==FX_KBD_PENDING||fx_keyboard_phase==FX_KBD_DONE){
            fx_keyboard_phase=FX_KBD_IDLE;memset(&fx_keyboard_req,0,sizeof(fx_keyboard_req));
            __atomic_store_n(&fx_keyboard_blocked,0,__ATOMIC_RELEASE);
        }
    }
    pthread_mutex_unlock(&fx_keyboard_lock);
}
static void fx_keyboard_cancel_all(void) {
    pthread_mutex_lock(&fx_keyboard_lock);
    if(fx_keyboard_phase!=FX_KBD_IDLE)memset(&fx_keyboard_result,0,sizeof(fx_keyboard_result));
    if(fx_keyboard_phase!=FX_KBD_IDLE&&fx_keyboard_phase!=FX_KBD_DONE){
        int abandoned=fx_keyboard_canceled;
        fx_keyboard_canceled=1;memset(&fx_keyboard_result,0,sizeof(fx_keyboard_result));
        fx_keyboard_phase=abandoned?FX_KBD_IDLE:FX_KBD_DONE;
    }
    __atomic_store_n(&fx_keyboard_blocked,0,__ATOMIC_RELEASE);
    __atomic_store_n(&fx_keyboard_manual_pending,0,__ATOMIC_RELEASE);
    fx_keyboard_delivery_done();
    pthread_mutex_unlock(&fx_keyboard_lock);
#ifdef FX_KEYBOARD_OVERLAY
    fx_osk_abort(0);
#endif
}
/* Called with the controller lock. No applet or keyboard mutex is acquired.
 * Once a chord is recognized, neutral input is delivered until release. */
static void fx_keyboard_poll_locked(void) {
    const uint64_t chord=FX_PAD_L|FX_PAD_R|FX_PAD_LSTICK;
    int held=0,clicked=0,neutral=1;
    for(unsigned i=0;i<2;i++){
        uint64_t buttons=fx_samples[i].connected?fx_samples[i].buttons:0;
        uint64_t pressed=buttons&~fx_keyboard_previous_buttons[i];
        fx_keyboard_previous_buttons[i]=buttons;
        if(i>=fx_players)continue;
        if((buttons&chord)==chord){held=1;if(pressed&FX_PAD_LSTICK)clicked=i+1;}
        if(!fx_pad_neutral(&fx_samples[i]))neutral=0;
    }
    if(!fx_game_active)return;
    if(held)
        __atomic_store_n(&fx_keyboard_shortcut_blocked,1,__ATOMIC_RELEASE);
    if(clicked&&!fx_pads_paused()&&!fx_keyboard_delivering()&&!__atomic_load_n(&fx_keyboard_blocked,__ATOMIC_ACQUIRE)
#ifdef FX_KEYBOARD_OVERLAY
       &&!fx_osk_blocked()
#endif
    ){
        __atomic_store_n(&fx_keyboard_manual_player,clicked-1,__ATOMIC_RELEASE);
        __atomic_store_n(&fx_keyboard_manual_pending,1,__ATOMIC_RELEASE);
    }
    if(neutral)__atomic_store_n(&fx_keyboard_shortcut_blocked,0,__ATOMIC_RELEASE);
}
static unsigned fx_keyboard_validation_limit;
static SwkbdTextCheckResult fx_keyboard_validate(char *text,size_t size) {
    uint16_t result[FX_TEXT_UNITS+1];
    if(fx_text_decode(text,size,result,fx_keyboard_validation_limit)>=0)return SwkbdTextCheckResult_OK;
    snprintf(text,size,"Text is too long or contains unsupported characters.");
    return SwkbdTextCheckResult_Bad;
}
static void fx_keyboard_service(void) {
    struct fx_text_request req;int show=0;
    pthread_mutex_lock(&fx_keyboard_lock);
    if(fx_keyboard_phase==FX_KBD_IDLE||fx_keyboard_phase==FX_KBD_DONE){
        pthread_mutex_unlock(&fx_keyboard_lock);return;
    }
    if(fx_keyboard_phase==FX_KBD_PENDING){
        if(fx_keyboard_canceled)fx_keyboard_phase=FX_KBD_DRAIN;
        else{req=fx_keyboard_req;fx_keyboard_phase=FX_KBD_SHOWING;show=1;}
    }
    pthread_mutex_unlock(&fx_keyboard_lock);
    if(show){
        SwkbdConfig config;char initial[FX_TEXT_BYTES],output[FX_TEXT_BYTES]={0};
        struct fx_text_result result={0};Result rc;
        fx_text_encode(req.initial,initial);
        pthread_mutex_lock(&fx_pad_applet_lock);
        rc=swkbdCreate(&config,0);
        if(R_SUCCEEDED(rc)){
            swkbdConfigMakePresetDefault(&config);
            swkbdConfigSetHeaderText(&config,"PES13 - FEXTendo");
            swkbdConfigSetGuideText(&config,"Enter text");
            swkbdConfigSetReturnButtonFlag(&config,0);
            swkbdConfigSetStringLenMin(&config,0);
            swkbdConfigSetStringLenMax(&config,req.limit);
            swkbdConfigSetInitialText(&config,initial);
            fx_keyboard_validation_limit=req.limit;
            swkbdConfigSetTextCheckCallback(&config,fx_keyboard_validate);
            /* TextCheck is a live request/reply while swkbd owns foreground.
             * AlwaysSuspend stops this process before it can acknowledge +,
             * so swkbd waits forever. Keep HOME/sleep suspension, but allow
             * our native worker to answer while the library applet is open.
             * Wine input/frame boundaries remain gated during this interval. */
            pthread_mutex_lock(&fx_pad_lock);
            __atomic_store_n(&fx_keyboard_applet_active,1,__ATOMIC_RELEASE);
            pthread_mutex_unlock(&fx_pad_lock);
            rc=appletSetFocusHandlingMode(AppletFocusHandlingMode_SuspendHomeSleep);
            if(R_SUCCEEDED(rc))rc=swkbdShow(&config,output,sizeof(output));
            Result restore=appletSetFocusHandlingMode(AppletFocusHandlingMode_AlwaysSuspend);
            if(R_FAILED(restore))rc=restore;
            swkbdClose(&config);
            pthread_mutex_lock(&fx_pad_lock);
            __atomic_store_n(&fx_keyboard_applet_active,0,__ATOMIC_RELEASE);
            pthread_cond_broadcast(&fx_pad_cond);
            pthread_mutex_unlock(&fx_pad_lock);
        }
        pthread_mutex_unlock(&fx_pad_applet_lock);
        if(R_SUCCEEDED(rc)&&fx_text_decode(output,sizeof(output),result.text,req.limit)>=0)result.accepted=1;
        pthread_mutex_lock(&fx_keyboard_lock);
        if(!fx_keyboard_canceled)fx_keyboard_result=result;
        fx_keyboard_phase=FX_KBD_DRAIN;
        pthread_mutex_unlock(&fx_keyboard_lock);
    }
    /* Poll only after returning from the applet. Reconnect takes precedence;
     * input used to dismiss the keyboard must never reach PES. */
    struct fx_pad_sample p[2];fx_pads_snapshot(p);
    if(fx_pads_paused()){fx_keyboard_cancel_all();return;}
    if(appletGetFocusState()!=AppletFocusState_InFocus)return;
    if(!fx_pad_neutral(&p[0])||(fx_pads_players()==2&&!fx_pad_neutral(&p[1])))return;
    pthread_mutex_lock(&fx_keyboard_lock);
    if(fx_keyboard_phase==FX_KBD_DRAIN){
        fx_keyboard_phase=fx_keyboard_canceled?FX_KBD_IDLE:FX_KBD_DONE;
        if(fx_keyboard_canceled)memset(&fx_keyboard_req,0,sizeof(fx_keyboard_req));
        __atomic_store_n(&fx_keyboard_blocked,0,__ATOMIC_RELEASE);
    }
    pthread_mutex_unlock(&fx_keyboard_lock);
}
