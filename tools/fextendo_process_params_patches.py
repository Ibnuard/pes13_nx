"""Reserve writable CWD capacity before the adjacent process-parameter strings.

Wine's SetCurrentDirectory writes into this buffer in place. The native
bootstrap previously reserved strlen(CWD)+1; Kitserver's longer directory
overwrote DllPath. Wine and WoW64 preserve MaximumLength when copying params.
"""


def apply(source):
    name = 'wine-nx-probe/source/runtime.c'
    path = source / name
    data = path.read_text()

    def replace(old, new):
        nonlocal data
        assert data.count(old) == 1, (old, data.count(old))
        data = data.replace(old, new)

    replace('static RTL_USER_PROCESS_PARAMETERS *runtime_create_process_params(',
            'static __attribute__((noinline)) RTL_USER_PROCESS_PARAMETERS *runtime_create_process_params(')
    replace('    size_t chars, size, i;\n    WCHAR *cursor;',
            '    size_t chars, size, i, current_dir_chars;\n    WCHAR *cursor;')
    replace('    chars = strlen( current_dir ) + 1;\n    chars += strlen( dll_path ) + 1;',
            '''    /* RtlSetCurrentDirectory_U writes a new directory in place. Match
     * RtlCreateProcessParametersEx's MAX_PATH reservation, including NUL;
     * never place DllPath immediately after the short initial CWD. Retain
     * larger capacity if the initial path itself already exceeds MAX_PATH. */
    current_dir_chars = max( (size_t)MAX_PATH, strlen( current_dir ) + 1 );
    chars = current_dir_chars;
    chars += strlen( dll_path ) + 1;''')
    replace('    put_process_string( &cursor, &params->CurrentDirectory.DosPath, current_dir );\n'
            '    put_process_string( &cursor, &params->DllPath, dll_path );',
            '''    put_process_string( &cursor, &params->CurrentDirectory.DosPath, current_dir );
    params->CurrentDirectory.DosPath.MaximumLength = current_dir_chars * sizeof(WCHAR);
    cursor = params->CurrentDirectory.DosPath.Buffer + current_dir_chars;
    put_process_string( &cursor, &params->DllPath, dll_path );''')
    replace('    params->EnvironmentSize = environment_bytes * sizeof(WCHAR);',
            '''    params->EnvironmentSize = environment_bytes * sizeof(WCHAR);
    log_line( "[PROCESS-PATH] v1 cwd_capacity_chars=%u dll_path_after_reserved_cwd=1",
              (unsigned)current_dir_chars );''')
    path.write_text(data)
    return {name}
