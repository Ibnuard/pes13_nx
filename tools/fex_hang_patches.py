"""Post-stability patch: remove scaled readback, propagate submit errors, capture idle workers."""
from fex_resume_patches import _function


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('hang audit: source drift at ' + old[:90])
    return text.replace(old, new)


def apply(read, replace, project):
    name = 'dlls/win32u/vulkan.c'
    source = read(name)
    start = source.index('static LONG nx_scaled_presents;')
    old = _function(source, 'nx_submit_scaled')
    end = source.index(old, start) + len(old)
    changed = source[:start] + (project / 'src/runtime/fex_scaled_submit.h').read_text() + source[end:]
    changed = once(changed,
        '        nx_submit_scaled( queue, &submit_info, blit_swapchain, blit_hack, &pool );',
        '        if ((res = nx_submit_scaled(queue, &submit_info))) goto failed;')
    # The readback path alone used these retained last-swapchain pointers.
    changed = once(changed, '    struct swapchain *blit_swapchain = NULL;\n    struct fs_hack_image *blit_hack = NULL;', '')
    changed = once(changed, '        blit_swapchain = swapchain;\n        blit_hack = hack;', '')
    replace(name, source, changed)

    name = 'wine-nx-probe/source/thread_profile.c'
    source = read(name)
    probe = (project / 'src/runtime/fex_stall_probe.h').read_text()
    enhanced = probe.replace('fex_stall_targets[4]', 'fex_stall_targets[64]')
    enhanced = enhanced.replace('i < 4', 'i < 64').replace('n < 4', 'n < 64')
    enhanced = once(enhanced, "rows[i].tid != 4 && rows[i].permille >= 30", "rows[i].tid != 4")
    enhanced = enhanced.replace('fill remaining slots from busiest Wine threads.',
                                'include sleeping Wine workers as potential lock owners.')
    enhanced = once(enhanced, 'struct fex_stall_capture captured[8] = {{0}};',
                    'static struct fex_stall_capture captured[128]; /* single log thread; avoid a large stack frame */')
    enhanced = once(enhanced, 'if (!pes13_fex_stall_due(&gate, presents, seconds)) return;',
        'if (!fex_hang_due(&gate, presents, seconds)) return;\n'
        '    memset(captured, 0, sizeof(captured));\n'
        '    wine_nx_thread_report(); /* refresh live handles, including blocked/idle workers */\n'
        '    wine_nx_fex_hang_waiters_report();')
    anchor = '#include "horizon_stall.h"'
    enhanced = once(enhanced, anchor, anchor + '\n' +
                    (project / 'src/runtime/fex_hang_gate.h').read_text() + '\n'
                    'extern void wine_nx_fex_hang_waiters_report(void);')
    replace(name, probe, enhanced)

    name = 'dlls/ntdll/unix/horizon.c'
    anchor = '/* FEX3_RESUME_GATE_END */'
    replace(name, anchor, (project / 'src/runtime/fex_hang_waiters.h').read_text() + '\n' + anchor)

    name = 'wine-nx-probe/source/runtime.c'
    anchor = '        if (ticks % 25 == 0)\n        {\n            extern unsigned int wine_nx_vk_presents __attribute__((weak));'
    replace(name, anchor, anchor.replace('ticks % 25', 'ticks % 5'))
    replace(name, '"pes13-fex3-stability-540p"', '"pes13-fex3-hang-audit"')
    anchor = '    log_line("[FEX3-RESUME] isolated self-suspend wake; final start-gate broadcast; 20ms recheck");'
    replace(name, anchor, anchor + '\n'
        '    log_line("[FEX3-SCALED] no diagnostic readback; blit submit failures propagate");\n'
        '    log_line("[FEX3-HANG] v2 capture after 3s no presents; includes idle workers, max 3 captures");')
