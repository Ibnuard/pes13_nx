"""Avoid periodic heap scans by declining the optional client budget extension."""


def apply(read, replace, project):
    name='wine-nx-probe/source/runtime.c'
    replace(name,'static int fex_gap_probe_enabled = 1;',
            'int wine_nx_fex_memory_budget_enabled = 0;\nstatic int fex_gap_probe_enabled = 1;')
    anchor='    fex_gap_probe_enabled = wine_nx_config_file_bool(RUNTIME_DIR "/fex_gap_probe", 1);'
    replace(name,anchor,
            '    wine_nx_fex_memory_budget_enabled = wine_nx_config_file_bool(RUNTIME_DIR "/fex_memory_budget", 0);\n'
            '    log_line("[FEX3-MEMBUDGET] client_extension=%d; 0 uses standard DXVK no-budget fallback, 1 restores driver queries", wine_nx_fex_memory_budget_enabled);\n'+anchor)
    replace(name,'"pes13-fextendo-mem-audit"','"pes13-fextendo-v3.2-glass"')
    name='dlls/win32u/vulkan.c'
    anchor='static VkResult init_physical_device( struct vulkan_physical_device *physical_device, VkPhysicalDevice host_physical_device,'
    replace(name,anchor,(project/'src/runtime/fex_memory_budget.h').read_text()+'\n'+anchor)
    anchor='    /* filter out unsupported client device extensions */'
    replace(name,anchor,'    wine_nx_fex_filter_client_budget( &extensions );\n\n'+anchor)
