/* Model display/services while running the actual startup screen lifecycle. */
#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include "../src/runtime/fextendo_launch_memory.h"
#include "../src/runtime/fextendo_runtime_api.h"
typedef uint64_t u64;typedef int Result;
typedef struct{int unused;}PadState;
typedef struct{int consoleInitialised;}PrintConsole;
typedef struct{int id;}devoptab_t;
typedef struct{int unused;}ErrorApplicationConfig;
static const devoptab_t silent={1},output={2};
static const devoptab_t *devoptab_list[]={&silent,&silent,&silent};
#define STD_OUT 1
#define HidNpadStyleSet_NpadStandard 0
#define HidNpadButton_A 1
#define HidNpadButton_B 2
#define HidNpadButton_Plus 4
#define R_SUCCEEDED(r) ((r)==0)
static const char *root;
#define RUNTIME_DIR root
static struct fx_launch_memory fx_startup_memory;
static int kind,opens,closes,popups,probes,checked;
static PrintConsole display;
static void fx_launch_memory_read(void){}
static int fxt_low_window_layout(uint64_t b,uint64_t s){return b==0x200000&&b+s==(1ull<<39);}
static int fxt_low_window_preflight(void){probes++;return kind!=3;}
static PrintConsole *consoleInit(void *p){(void)p;opens++;display.consoleInitialised=1;if(opens==1)devoptab_list[STD_OUT]=&output;return &display;}
static void consoleExit(void *p){(void)p;assert(display.consoleInitialised);display.consoleInitialised=0;closes++;}
static void consoleClear(void){}
static void consoleUpdate(void *p){(void)p;assert(devoptab_list[STD_OUT]==&output);}
static void padConfigureInput(int count,int style){(void)count;(void)style;}
static void fx_pads_init(void){}
static void padInitializeDefault(PadState *p){(void)p;}
static void padUpdate(PadState *p){(void)p;}
static u64 padGetButtonsDown(PadState *p){(void)p;return popups?HidNpadButton_B:0;}
static int appletMainLoop(void){return 1;}
static u64 armGetSystemTick(void){return 1;}
static u64 armTicksToNs(u64 n){return n;}
static void svcSleepThread(u64 n){(void)n;}
static int errorApplicationCreate(ErrorApplicationConfig *c,const char *m,const char *d){(void)c;(void)m;(void)d;popups++;return 0;}
static void errorApplicationShow(ErrorApplicationConfig *c){(void)c;assert(!display.consoleInitialised);}
int fx_runtime_recover(struct fxr_job *j){(void)j;return 1;}
int fx_runtime_check(struct fxr_job *j){assert(display.consoleInitialised);checked++;j->progress(FXR_CHECK,1,1,"");j->changed=0;if(kind==4){snprintf(j->error,sizeof(j->error),"Repair error");return 0;}return 1;}
int fx_runtime_repair(struct fxr_job *j){(void)j;abort();}
unsigned fx_runtime_file_count(void){return 1;}
#include "../src/runtime/fextendo_startup_switch.h"
int main(int argc,char **argv){
    assert(argc==3);root=argv[1];kind=atoi(argv[2]);
    fx_startup_memory=(struct fx_launch_memory){.base=kind==1?0x8000000:0x200000,
        .size=(kind==0?(1ull<<32):(1ull<<39))-(kind==1?0x8000000:0x200000)};
    assert(fx_startup_switch()==(kind!=4));
    assert(!display.consoleInitialised&&devoptab_list[STD_OUT]==&silent&&opens==closes);
    if(kind==0)assert(fx_boot_launch_ready&&!fx_boot_patch_active&&!probes);
    if(kind==1)assert(!fx_boot_launch_ready&&!fx_boot_patch_active&&!probes);
    if(kind==2)assert(fx_boot_launch_ready&&fx_boot_patch_active&&probes==1);
    if(kind==3)assert(!fx_boot_launch_ready&&!fx_boot_patch_active&&probes==1);
    if(kind==4)assert(popups==1&&opens==2&&checked==1);
    puts("PASS: boot status, low-window preflight routing, popup, console/stdout handoff");return 0;
}
