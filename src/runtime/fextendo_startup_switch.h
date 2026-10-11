/* SPDX-License-Identifier: LGPL-2.1-or-later. Runs before artwork and Wine.
 * A built-in console can repair missing launcher artwork too. It relinquishes
 * the window before the GUI starts. No diagnostic files are opened here. */
#ifndef FEXTENDO_STARTUP_SWITCH_H
#define FEXTENDO_STARTUP_SWITCH_H
#include "fextendo_startup_check.h"
static int fx_boot_patch_active,fx_boot_launch_ready,fx_check_cancelled,fx_check_console;
static PadState fx_check_pad;
static uint64_t fx_check_draw_tick;
static const devoptab_t *fx_check_previous_stdout,*fx_check_console_stdout;
static int fx_check_open(void){
    PrintConsole *c=consoleInit(NULL);
    if(!fx_check_console_stdout)fx_check_console_stdout=devoptab_list[STD_OUT];
    devoptab_list[STD_OUT]=fx_check_console_stdout;
    return c&&c->consoleInitialised;
}
static void fx_check_close(void){
    if(fx_check_console)consoleExit(NULL);
    devoptab_list[STD_OUT]=fx_check_previous_stdout;fx_check_console=0;
}
static int fx_check_poll(void){
    if(!appletMainLoop())fx_check_cancelled=1;
    padUpdate(&fx_check_pad);
    if(padGetButtonsDown(&fx_check_pad)&(HidNpadButton_B|HidNpadButton_Plus))fx_check_cancelled=1;
    return fx_check_cancelled;
}
static void fx_check_progress(int phase,uint64_t current,uint64_t total,const char *name){
    (void)name;
    static const char *const labels[]={"Checking runtime","Downloading runtime","Verifying runtime","Installing runtime","Recovering runtime"};
    if(!fx_check_console)return;
    uint64_t now=armGetSystemTick();
    if(fx_check_draw_tick&&current!=total&&armTicksToNs(now-fx_check_draw_tick)<200000000ull)return;
    fx_check_draw_tick=now;
    printf("\x1b[7;1H\x1b[2K%s: %u%%\n",labels[phase],total?(unsigned)(current*100/total):0);
    printf("\x1b[9;1H\x1b[2KMissing or changed runtime files are repaired automatically.\n");
    printf("\x1b[11;1H\x1b[2KWi-Fi is only needed for repair. B / + cancels safely.\n");
    consoleUpdate(NULL);
}
static int fx_startup_switch(void){
    fx_launch_memory_read();
    int mode=fx_memory_mode(&fx_startup_memory);
    /* A matching process layout is necessary, but verify low RX/RW aliases
     * and native placement before calling the boot patch active. */
    fx_boot_patch_active=mode==FX_MEMORY_39&&
        fxt_low_window_layout(fx_startup_memory.base,fx_startup_memory.size)&&fxt_low_window_preflight();
    fx_boot_launch_ready=mode==FX_MEMORY_32_NO_ALIAS||fx_boot_patch_active;
    fx_check_previous_stdout=devoptab_list[STD_OUT];
    fx_check_console=fx_check_open();
    /* Keep the shared two-player HID configuration. Configuring one pad
     * here would reset supported IDs and could make Player 2 disappear. */
    fx_pads_init();padInitializeDefault(&fx_check_pad);
    for(;;){
        fx_check_cancelled=0;fx_check_draw_tick=0;
        if(fx_check_console){
            consoleClear();printf("FEXTendo | Startup checks\n\n");
            printf("Memory: %s\nFEXTendo Patch: %s\n",fx_memory_mode_name(mode),
                fx_boot_patch_active?"active - High available":"inactive - High locked");
            consoleUpdate(NULL);
        }
        struct fxr_job job={.root=RUNTIME_DIR,.progress=fx_check_progress,.cancelled=fx_check_poll};
        int ok=fx_startup_check(&job);
        if(ok||fx_check_cancelled){
            fx_check_close();return ok&&!fx_check_cancelled;
        }
        fx_check_close();
        ErrorApplicationConfig popup;
        const char *details="Expected game: /switch/pes13-fex/drive_c/PES13/pes2013.exe and its img folder.\nRuntime repair uses the official pinned GitHub release. Game files and saves are preserved.\nConnect Wi-Fi, check SD space and the system date, then retry.";
        if(R_SUCCEEDED(errorApplicationCreate(&popup,job.error,details)))errorApplicationShow(&popup);
        /* No artwork is assumed to exist. A retry is also available when
         * launching as an applet that cannot open the error applet. */
        fx_check_console=fx_check_open();
        if(!fx_check_console){fx_check_close();return 0;}
        consoleClear();printf("FEXTendo | Startup check failed\n\n%s\n\n%s\n\nA: retry checks / B or +: close\n",job.error,details);consoleUpdate(NULL);
        int retry=0;
        while(appletMainLoop()){
            padUpdate(&fx_check_pad);u64 down=padGetButtonsDown(&fx_check_pad);
            if(down&HidNpadButton_A){retry=1;break;}
            if(down&(HidNpadButton_B|HidNpadButton_Plus))break;
            svcSleepThread(20000000);
        }
        if(!retry){fx_check_close();return 0;}
    }
}
#endif
