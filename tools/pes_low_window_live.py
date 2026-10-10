"""LW3: observe the patched game's live settings and attribute loading calls.

No assumed frame-skip bit change: the supplied pair is independently audited
against Settings.exe. No memory-layout/engine/renderer/time-policy changes.
"""
import shutil
from fextendo_low_window import ROOT, exact


def apply_wait_attribution(text):
    """Keep LW3's Vulkan attribution when a later revision updates the observer."""
    anchor='    __atomic_store_n(&r->end,FX_WAIT_NOW(),__ATOMIC_RELAXED);'
    return exact(text,anchor,anchor+'''
    if(__atomic_load_n(&r->kind,__ATOMIC_RELAXED)==2){
        uint64_t start=__atomic_load_n(&r->begin,__ATOMIC_RELAXED);
        uint64_t finish=__atomic_load_n(&r->end,__ATOMIC_RELAXED);
        if(finish>=start)pes_vk_work_add(__atomic_load_n(&r->thread,__ATOMIC_RELAXED),
            __atomic_load_n(&r->code,__ATOMIC_RELAXED),finish-start);
    }''')


def apply(source,feature):
    runtime=source/'wine-nx-probe/source/runtime.c'
    text=runtime.read_text()
    text=exact(text,'#define FX_APP_VERSION "0.3.9-lw2"','#define FX_APP_VERSION "0.3.9-lw3"')
    # Include before the existing call-end producer, after debug logging.
    text=exact(text,'#include "fextendo_wait_probe.h"',
               (ROOT/'src/runtime/pes_vk_work.h').read_text()+'\n#include "fextendo_wait_probe.h"')
    wait_header=feature/'fextendo_wait_probe.h'
    wait_text=wait_header.read_text()
    wait_text=apply_wait_attribution(wait_text)
    anchor='static void __attribute__((noinline)) fx_low_window_diagnostics(unsigned ticks)'
    text=exact(text,anchor,(ROOT/'src/runtime/pes_live_settings.h').read_text()+'\n'+anchor)
    text=exact(text,'    if(ticks%25==0)fex_game_timing_report();',
               '    if(ticks%25==0){pes_live_settings_report();pes_vk_work_report();}')
    # The old 1.00-only object snapshot is retained in source but not scheduled
    # for the patched 1.03 game. Do not present a disk check as a live check.
    text=exact(text,'[FEX3-GAME] enabled=%d; LW2 Debug-only 5s read-only guest settings/timing; no speed scaling',
               '[LW3-LIVESET] enabled=%d; Debug-only 5s WECF reads for 1.00/1.03/1.04; no guest writes or clock scaling')
    runtime.write_text(text)
    wait_header.write_text(wait_text)
    for n in ('pes_live_settings.h','pes_vk_work.h'):
        shutil.copy2(ROOT/'src/runtime'/n,feature/n)
