#ifndef WINE_NX_LSFG_CONFIG_H
#define WINE_NX_LSFG_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

void wine_nx_lsfg_configure(int enabled, int performance, int flow);
/* Cached shader-payload validation. No DLL code is executed or GPU work done. */
int wine_nx_lsfg_available(void);
const char *wine_nx_lsfg_unavailable_reason(void);

#ifdef __cplusplus
}
#endif
#endif
