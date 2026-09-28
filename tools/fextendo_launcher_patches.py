"""Add the controller launcher without keeping UI workers alive in gameplay."""

def apply(read,replace,project):
    name='wine-nx-probe/source/runtime.c'
    headers=('fextendo_presets.h','fextendo_ui.h','fextendo_timestamp_pixels.h','fextendo_overlay_layer.h','fextendo_timestamp.h','fextendo_sfx.h','fextendo_launcher.h')
    body='\n'.join((project/'src/runtime'/p).read_text() for p in headers)
    replace(name,'static void log_line(const char *fmt, ...);','static void log_line(const char *fmt, ...);\n'+body)
    replace(name,'static int wine_nx_console_active = 1;','static int wine_nx_console_active = 0;')
    replace(name,'    consoleInit( NULL );','    /* Fextendo owns the initial display; debug output remains in the log. */')
    anchor='    const int guest_tests = wine_nx_config_file_bool(RUNTIME_DIR "/run-guest-tests.txt", 1);'
    replace(name,anchor,anchor.replace(', 1);',', 0);')+'\n'
            '    if (guest_tests) { consoleInit(NULL); wine_nx_console_active = 1; }\n'
            '    else if (!fx_launcher_start()) return 0;\n')
    replace(name,'int wine_nx_fb_init(void)\n{\n    Result rc;',
            'int wine_nx_fb_init(void)\n{\n    Result rc;\n    if (fx_owned()) return -1;')
    replace(name,'void *wine_nx_fb_lock( int *width, int *height, int *stride_px )\n{',
            'void *wine_nx_fb_lock( int *width, int *height, int *stride_px )\n{\n    if (fx_owned()) return NULL; /* suppress intermediate desktop/GDI windows */')
    replace(name,'    if (!wine_nx_compositor_mode) return 0;',
            '    if (fx_owned() || !wine_nx_compositor_mode) return 0;')
    replace(name,'void *wine_nx_gl_acquire_window(void)\n{',
            'void *wine_nx_gl_acquire_window(void)\n{\n    if (!fx_handoff()) return NULL;')
    replace(name,'static void park_forever(void)\n{',
            'static void park_forever(void)\n{\n    fx_fail("PES13 could not start. Check fex-runtime.log.");')
    replace(name,'    fex_gap_present(queue, swapchain, 1);',
            '    fex_gap_present(queue, swapchain, 1);\n    fx_record_first_present();')
    replace(name,'static void fex_frame_report(void)\n{',
            'static void fex_frame_report(void)\n{\n    fx_history_flush();')
    replace(name,'    if (!pes13_fex_context_preflight()) park_forever();',
            '    fx_stage("Preparing your game...");\n    if (!pes13_fex_context_preflight()) park_forever();')
    replace(name,'    wine_nx_runtime_platform_init();',
            '    fx_stage("Loading game files...");\n    wine_nx_runtime_platform_init();')
    replace(name,'    status = map_pe_image( target, &module, &view_size );',
            '    fx_stage("Starting PES13...");\n    status = map_pe_image( target, &module, &view_size );')
    replace(name,'"pes13-fex3-gap-audit"','"pes13-fextendo-v1"')
