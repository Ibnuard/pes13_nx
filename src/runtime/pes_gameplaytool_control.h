/* LGPL-2.1-or-later. Startup-only optional Gameplay Tool isolation.
 * Uses Wine's ordinary disabled-DLL policy. No game DLL, registry, clock,
 * renderer or asset file is modified. An explicit config opt-in restores
 * Gameplaytool.dll for a same-NRO comparison after restarting. */
#ifndef PES_GAMEPLAYTOOL_CONTROL_H
#define PES_GAMEPLAYTOOL_CONTROL_H
#include <stdlib.h>
#include <string.h>

static int __attribute__((noinline)) pes_gameplaytool_control(int guest_tests, int enable_tool)
{
    static const char rule[]="gameplaytool,*gameplaytool=";
    char overrides[4096];
    const char *old;
    size_t n=0;
    if(guest_tests||enable_tool)return 1;
    old=getenv("WINEDLLOVERRIDES");
    if(old){
        while(n<sizeof(overrides)&&old[n])n++;
        if(n+1+sizeof(rule)>sizeof(overrides))return 0;
        memcpy(overrides,old,n);
    }
    if(n)overrides[n++]=';';
    memcpy(overrides+n,rule,sizeof(rule));
    return setenv("WINEDLLOVERRIDES",overrides,1)==0;
}
#endif
