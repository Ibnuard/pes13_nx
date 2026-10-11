/* SPDX-License-Identifier: LGPL-2.1-or-later. Bounded startup work only. */
#ifndef FEXTENDO_STARTUP_CHECK_H
#define FEXTENDO_STARTUP_CHECK_H
#include "fextendo_install_check.h"
#include "fextendo_runtime_api.h"

/* Keep the same pinned catalog through recovery, repair and final recheck. */
static int fx_startup_check(struct fxr_job *job){
    if(!fx_install_check(job->root,job->error,sizeof(job->error)))return 0;
    if(!fx_runtime_recover(job)||!fx_runtime_check(job))return 0;
    if(!job->changed)return 1; /* Offline healthy launch: no filesystem writes. */
    if(!fx_runtime_repair(job)){
        char original[sizeof(job->error)];snprintf(original,sizeof(original),"%s",job->error);
        /* Recover any interrupted transaction before presenting Retry. */
        if(fx_runtime_recover(job))snprintf(job->error,sizeof(job->error),"%s",original);
        return 0;
    }
    if(!fx_runtime_check(job))return 0;
    if(job->changed){snprintf(job->error,sizeof(job->error),"Runtime verification failed after repair. Check the SD card.");return 0;}
    return 1;
}
static int fx_high_allowed(int patch_active,int preset){return preset!=3||patch_active;}
#define FX_HIGH_LOCK_MESSAGE "High requires an active FEXTendo Patch and the PES13 39-bit HOME tile. Reboot into FEXTendo Patch, or select Medium/Low."
#endif
