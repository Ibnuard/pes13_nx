/* LGPL-2.1-or-later. libnx opens Default before main for nwindowGetDefault.
 * Capture that successful handle via --wrap=viOpenDisplay and borrow it. Opening
 * Default again on the same VI session failed with 0x1272 on the tested Switch.
 * The overlay must never close this borrowed display or the game's window. */
static ViDisplay fx_default_display;
static int fx_default_display_ready;
extern Result __real_viOpenDisplay(const char *name,ViDisplay *display);
Result __wrap_viOpenDisplay(const char *name,ViDisplay *display) {
    Result rc=__real_viOpenDisplay(name,display);
    if(R_SUCCEEDED(rc)&&!strcmp(name,"Default")){
        fx_default_display=*display;
        __atomic_store_n(&fx_default_display_ready,1,__ATOMIC_RELEASE);
    }
    return rc;
}
static Result fx_overlay_display_open(ViDisplay *display,int *borrowed) {
    *borrowed=__atomic_load_n(&fx_default_display_ready,__ATOMIC_ACQUIRE);
    if(*borrowed){*display=fx_default_display;return 0;}
    return viOpenDefaultDisplay(display);
}
