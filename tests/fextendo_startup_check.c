/* Exercise real startup admission and repair orchestration with failed services. */
#include <assert.h>
#include "../src/runtime/fextendo_startup_check.h"
static int kind,checks,repairs,recovers;
int fx_runtime_recover(struct fxr_job *j){recovers++;if(kind==6){snprintf(j->error,sizeof(j->error),"Recovery blocked");return 0;}return 1;}
int fx_runtime_check(struct fxr_job *j){
    checks++;j->changed=(kind==1||kind==2||kind==5)&&(checks==1||kind==5);
    if(kind==3){snprintf(j->error,sizeof(j->error),"Unreadable runtime");return 0;}return 1;
}
int fx_runtime_repair(struct fxr_job *j){repairs++;if(kind==2){snprintf(j->error,sizeof(j->error),"Network unavailable");return 0;}return 1;}
unsigned fx_runtime_file_count(void){return 1;}
int main(int argc,char **argv){
    assert(argc==3);kind=atoi(argv[2]);struct fxr_job j={.root=argv[1]};
    int ok=fx_startup_check(&j);
    if(kind==0)assert(ok&&checks==1&&!repairs&&recovers==1);
    else if(kind==1)assert(ok&&checks==2&&repairs==1&&recovers==1);
    else if(kind==2)assert(!ok&&checks==1&&repairs==1&&recovers==2&&!strcmp(j.error,"Network unavailable"));
    else if(kind==3)assert(!ok&&!repairs);
    else if(kind==4)assert(!ok&&!checks&&!repairs&&!recovers&&strstr(j.error,"Installation is not correct"));
    else if(kind==5)assert(!ok&&checks==2&&repairs==1);
    else if(kind==6)assert(!ok&&!checks&&!repairs);
    for(int active=0;active<2;active++)for(int preset=0;preset<4;preset++)
        assert(fx_high_allowed(active,preset)==(preset!=3||active));
    printf("PASS startup scenario=%d: %s\n",kind,j.error);return 0;
}
