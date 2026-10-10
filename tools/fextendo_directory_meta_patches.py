"""Reuse libnx's enumerated file size; retain real timestamps and Wine attributes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(source):
    changed = set()

    def edit(name, fn):
        p = source / name
        before = p.read_text()
        after = fn(before)
        assert before != after, name
        p.write_text(after)
        changed.add(name)

    def one(data, old, new):
        assert data.count(old) == 1, (old[:120], data.count(old))
        return data.replace(old, new)

    for name in ('horizon_directory_meta.h', 'horizon_directory_meta.c'):
        dest = 'dlls/ntdll/unix/' + name
        (source / dest).write_bytes((ROOT / 'src/runtime' / name).read_bytes())
        changed.add(dest)

    def horizon(data):
        data = one(data, 'struct horizon_directory_file_entry\n{\n    unsigned int name_len;\n};',
                   '#include "horizon_directory_meta.c"')
        data = one(data, '        dir_entry.name_len = name_len;',
                   '        horizon_dir_capture_metadata(object->dir_stream, object->file_name, name, &dir_entry);\n'
                   '        dir_entry.name_len = name_len;')
        return data
    edit('dlls/ntdll/unix/horizon.c', horizon)

    def file(data):
        data = one(data, '# include "horizon_private.h"',
                   '# include "horizon_private.h"\n# include "horizon_directory_meta.h"')
        data = one(data, 'static int get_file_info( const char *path, struct stat *st, ULONG *attr, ULONG *reparse_tag )\n{',
                   'static int get_file_info_with_stat( const char *path, struct stat *st, ULONG *attr, ULONG *reparse_tag,\n'
                   '                                    const struct stat *known )\n{')
        data = one(data, '    ret = lstat( path, st );\n#ifdef __SWITCH__\n    if (ret == -1 && errno == EIO) ret = horizon_stat_open_file( path, st );\n#endif',
                   '    if (known) { *st = *known; ret = 0; }\n'
                   '    else\n    {\n        ret = lstat( path, st );\n#ifdef __SWITCH__\n'
                   '        if (ret == -1 && errno == EIO) ret = horizon_stat_open_file( path, st );\n#endif\n    }')
        start = data.index('static int get_file_info_with_stat(')
        end = data.index('\n}\n', start) + 3
        data = (data[:end] + '\nstatic int get_file_info( const char *path, struct stat *st, ULONG *attr, ULONG *reparse_tag )\n{\n'
                + '    return get_file_info_with_stat(path, st, attr, reparse_tag, NULL);\n}\n' + data[end:])
        old = '''static NTSTATUS get_dir_data_entry( struct dir_data *dir_data, void *info_ptr, IO_STATUS_BLOCK *io,
                                    ULONG max_length, FILE_INFORMATION_CLASS class,
                                    union file_directory_info **last_info )'''
        data = one(data, old, old.replace('get_dir_data_entry(', 'get_dir_data_entry_with_stat(')
                   .replace('**last_info )', '**last_info, const struct stat *known )'))
        data = one(data, '    if (get_file_info( names->unix_name, &st, &attributes, &reparse_tag ) == -1)',
                   '    if (get_file_info_with_stat( names->unix_name, &st, &attributes, &reparse_tag, known ) == -1)')
        start = data.index('static NTSTATUS get_dir_data_entry_with_stat(')
        end = data.index('\n}\n', start) + 3
        data = (data[:end] + '\n' + old + '\n{\n'
                + '    return get_dir_data_entry_with_stat(dir_data, info_ptr, io, max_length, class, last_info, NULL);\n}\n' + data[end:])
        start = data.index('static NTSTATUS horizon_query_directory_file(')
        end = data.index('\n}\n', start) + 3
        block = data[start:end].replace('struct directory_file_entry', 'struct horizon_directory_file_entry')
        block = one(block, '        char *unix_name;', '        char *unix_name;\n        struct stat known;\n        int hint;\n'
                    '        unsigned token = horizon_dir_diag_begin(wine_server_obj_handle(handle));')
        block = one(block, '        if (status) break;', '        if (status) { horizon_dir_diag_end(token, -1); break; }')
        block = one(block, '        if (!dir_name && (status = server_get_unix_name( handle, &dir_name ))) break;',
                    '        horizon_dir_diag_stage(token, 2);\n'
                    '        if (!dir_name && (status = server_get_unix_name( handle, &dir_name )))\n'
                    '        { horizon_dir_diag_end(token, -1); break; }')
        assert block.count('            status = STATUS_NO_MEMORY;') == 2
        block = block.replace('            status = STATUS_NO_MEMORY;',
                              '            horizon_dir_diag_end(token, -1);\n            status = STATUS_NO_MEMORY;')
        block = one(block, '        status = get_dir_data_entry( &data, buffer, io, length, info_class, &last_info );',
                    '        horizon_dir_diag_stage(token, 3);\n'
                    '        hint = horizon_dir_entry_stat(unix_name, entry, &known, token);\n'
                    '        status = get_dir_data_entry_with_stat( &data, buffer, io, length, info_class, &last_info, hint ? &known : NULL );\n'
                    '        if (hint == 2 && last_info && info_class != FileNamesInformation)\n'
                    '        {\n'
                    '            last_info->dir.CreationTime.QuadPart = 0;\n'
                    '            last_info->dir.LastAccessTime.QuadPart = 0;\n'
                    '            last_info->dir.LastWriteTime.QuadPart = 0;\n'
                    '            last_info->dir.ChangeTime.QuadPart = 0;\n'
                    '        }\n'
                    '        horizon_dir_diag_end(token, hint);')
        data = data[:start] + block + data[end:]
        return data
    edit('dlls/ntdll/unix/file.c', file)

    def runtime(data):
        data = one(data, '        if(ticks%5==0)fx_debug_file_tick();',
                   '        if(ticks%25==0) { extern void horizon_dir_diag_tick(void); horizon_dir_diag_tick(); }\n'
                   '        if(ticks%5==0)fx_debug_file_tick();')
        data = one(data, '    wine_nx_runtime_trace("[HZDIR] v2 persistent directory cursor; bounded trace");',
                   '    {\n'
                   '        extern void horizon_dir_set_asset_scan(int enabled);\n'
                   '        int fast_scan = wine_nx_config_file_bool(RUNTIME_DIR "/kitserver_fast_scan", 1);\n'
                   '        horizon_dir_set_asset_scan(fast_scan);\n'
                   '        log_line("[HZDIR] v4 asset_scan=%d; Kitserver img names without timestamp IPC; ordinary file times preserved", fast_scan);\n'
                   '    }')
        return data
    edit('wine-nx-probe/source/runtime.c', runtime)
    return changed
