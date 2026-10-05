/* LGPL-2.1-or-later. Native-only repair API; independent of Wine/Windows macros. */
#ifndef FEXTENDO_RUNTIME_API_H
#define FEXTENDO_RUNTIME_API_H
#include <stdint.h>
enum fxr_phase {FXR_CHECK,FXR_DOWNLOAD,FXR_VERIFY,FXR_INSTALL,FXR_RECOVER};
struct fxr_job {
    const char *root;
    void (*progress)(int phase,uint64_t current,uint64_t total,const char *name);
    int (*cancelled)(void);
    unsigned char flags[256];
    unsigned changed;
    char error[192];
};
int fx_runtime_recover(struct fxr_job *job);
int fx_runtime_check(struct fxr_job *job);
int fx_runtime_repair(struct fxr_job *job);
unsigned fx_runtime_file_count(void);
#endif
