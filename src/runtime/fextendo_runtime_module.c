/* LGPL-2.1-or-later. Compile outside Wine's Windows include environment. */
#include "fextendo_runtime_download.h"
int fx_runtime_recover(struct fxr_job *job){return fxr_recover(job);}
int fx_runtime_check(struct fxr_job *job){return fxr_check(job);}
int fx_runtime_repair(struct fxr_job *job){return fxr_repair(job);}
unsigned fx_runtime_file_count(void){return FXR_COUNT;}
