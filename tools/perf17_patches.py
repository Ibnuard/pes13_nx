"""Narrow PERF17 additions composed after the stable PERF15 recipe."""
from pathlib import Path


def once(text, old, new):
    assert text.count(old) == 1, (old[:150], text.count(old))
    return text.replace(old, new, 1)


def adapt_recipe(recipe):
    recipe = recipe.replace('runtime-perf14-map-guards', 'runtime-perf17-hotblocks')
    recipe = recipe.replace('pes13-nx-0.2.0-perf14-map-guards', 'pes13-nx-0.2.0-perf17-hotblocks')
    recipe = recipe.replace('PES13-NX PERF14', 'PES13-NX PERF17')
    recipe = recipe.replace('local/perf14', 'local/perf17')
    recipe = recipe.replace('PERF14 NRO built', 'PERF17 NRO built')
    hook = '    cmake_source.write_text(cmake_text)'
    return once(recipe, hook,
                '    from perf17_patches import adapt as adapt_perf17\n'
                '    cmake_text, dynarec_text, runtime_text = adapt_perf17(cmake_text, dynarec_text, runtime_text, project)\n' + hook)


def adapt(cmake, dynarec, runtime, project):
    header = Path(project) / 'src/runtime/pes13_perf17.h'
    anchor = 'box64env_t *GetCurEnvByAddr( uintptr_t addr ) { return pes13_perf8_select_env(addr); }'
    dynarec = once(dynarec, 'unsigned long long wine_nx_box64_native_entries;',
                   f'void *DynarecMapWritableAddress(void *addr);\n#include "{header}"\n'
                   'unsigned long long wine_nx_box64_native_entries;')
    replacement = '''void wine_nx_perf17_bind_image(const char *path, void *base, size_t image_size)
{
    unsigned char header[512];
    size_t count = 0;
    char line[320];
    FILE *file = fopen(path, "rb");
    if (file) { count = fread(header, 1, sizeof(header), file); fclose(file); }
    int identity = pes17_bind_header(header, count, (uintptr_t)base, image_size);
    /* runtime_describe_image just validated this readable mapped image. */
    uint32_t loaded = image_size >= 512 ? pes17_header_hash(base, 512) : 0;
    snprintf(line, sizeof(line),
             "[PERF17-IMAGE] source=file header_bytes=%lu disk_hash=%08x loaded_hash=%08x base=%lx image_size=%lx identity=%d",
             (unsigned long)count, pes17_header_hash(header, count), loaded,
             (unsigned long)(uintptr_t)base, (unsigned long)image_size, identity);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}

box64env_t *GetCurEnvByAddr( uintptr_t addr )
{
    return pes17_select(addr, pes13_perf8_select_env(addr));
}'''
    dynarec = once(dynarec, anchor, replacement)
    dynarec = once(dynarec, '    apply_box64_options();', '''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf17-hotblocks.txt", "r");
        if (f) { __atomic_store_n(&pes17_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
        f = fopen("sdmc:/switch/pes13-nx/perf17-capture.txt", "r");
        if (f) { __atomic_store_n(&pes17_capture, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    hook = '''    wine_nx_box64_patch(native_source
        "    redundant_helper = current_helper = NULL;\\n${to_exec}    //block->done = 1;\\n    return block;\\n}"
        "    redundant_helper = current_helper = NULL;\\n${to_exec}    { extern void wine_nx_perf17_capture(void*, unsigned int); wine_nx_perf17_capture(block, helper.env->dynarec_bigblock); }\\n    //block->done = 1;\\n    return block;\\n}"
        "PERF17 bounded hotspot snapshots")
    wine_nx_box64_patch(native_source
        "    helper.need_reloc = IsAddrNeedReloc(addr);"
        "    { extern uintptr_t wine_nx_perf17_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf17_block_end(addr, helper.end, helper.env); }\\n    helper.need_reloc = IsAddrNeedReloc(addr);"
        "PERF17 bound hotspot block extension")
'''
    cmake = once(cmake, '    set(native_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_native.c")',
                 hook + '    set(native_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_native.c")')
    runtime = once(runtime, '    wine_nx_thread_report();\n}',
                   '    wine_nx_thread_report();\n    { extern void wine_nx_perf17_report(void); wine_nx_perf17_report(); }\n}')
    runtime = once(runtime,
                   '    if (runtime_describe_image( module, view_size, &entry ))\n    {',
                   '    if (runtime_describe_image( module, view_size, &entry ))\n    {\n'
                   '        { extern void wine_nx_perf17_bind_image(const char *, void *, size_t);\n'
                   '          wine_nx_perf17_bind_image(target, module, view_size); }')
    return cmake, dynarec, runtime
