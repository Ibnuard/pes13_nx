/* SPDX-License-Identifier: LGPL-2.1-or-later. Shared GUI checker snapshot. */
#ifndef FEXTENDO_STARTUP_VIEW_H
#define FEXTENDO_STARTUP_VIEW_H
enum fx_check_phase { FX_CHECK_BOOT,FX_CHECK_GAME,FX_CHECK_RUNTIME,
    FX_CHECK_DOWNLOAD,FX_CHECK_VERIFY,FX_CHECK_INSTALL,FX_CHECK_RECOVER,FX_CHECK_ART };
struct fx_check_view {
    int visible,failed,complete,phase,percent,memory_done,game_done,runtime_done,cached;
    char error[192];
};
#endif
