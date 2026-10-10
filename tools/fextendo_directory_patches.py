"""Keep a bounded directory cursor on the server object instead of rescanning.

The object mutex serializes queries through duplicated handles. A pending name
belongs to the open DIR until a reply succeeds, so short buffers and allocation
failures can retry without losing an entry. No directory-sized name cache.
"""


def apply(source):
    name = 'dlls/ntdll/unix/horizon.c'
    path = source / name
    text = path.read_text()

    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, (name, old[:100], text.count(old))
        text = text.replace(old, new)

    replace('    char *dir_mask;\n', '''    char *dir_mask;
    DIR *dir_stream;
    const char *dir_pending_name;   /* literal dot entry or storage owned by dir_stream */
    unsigned int dir_scan_index;
    unsigned int dir_trace_queries;
    int dir_scan_done;
''')
    replace('/* Callers hold horizon_server_objects_mutex. */\nstatic void horizon_server_free_object(', '''/* Callers hold horizon_server_objects_mutex. The stream belongs to the
 * object, not one handle: duplicates share enumeration and final cleanup. */
static void horizon_server_reset_directory( struct horizon_server_object *object )
{
    if (object->dir_stream) closedir( object->dir_stream );
    object->dir_stream = NULL;
    object->dir_pending_name = NULL;
    object->dir_scan_index = 0;
    object->dir_scan_done = 0;
}

/* Callers hold horizon_server_objects_mutex. */
static void horizon_server_free_object(''')
    replace('    free( object->dir_mask );\n    free( object->name );',
            '    horizon_server_reset_directory( object );\n    free( object->dir_mask );\n    free( object->name );')
    start = text.index('static int horizon_server_handle_query_directory_file(')
    end = text.index('\n}\n', start) + 3
    old = text[start:end]
    new = old.replace('    DIR *dir = NULL;\n    unsigned int raw_index = 0;\n',
                      '    int trace_query = 1;\n')
    new = new.replace('        if (request->restart_scan) object->dir_enum_index = 0;', '''        if (request->restart_scan || (mask_changed &&
            ((object->dir_mask && !new_mask) || (!object->dir_mask && new_mask) ||
             (object->dir_mask && new_mask && strcmp( object->dir_mask, new_mask )))))
            horizon_server_reset_directory( object );
        if (request->restart_scan) object->dir_enum_index = 0;''')
    new = new.replace('        if (!(dir = opendir( object->file_name ))) reply.header.error = horizon_server_errno_status( errno );', '''        if (!object->dir_stream && !object->dir_scan_done &&
            !(object->dir_stream = opendir( object->file_name )))
            reply.header.error = horizon_server_errno_status( errno );''')
    block_start = new.index('        const char *name = NULL;')
    block_end = new.index('        name_len = horizon_server_utf16_name_len( name );', block_start)
    new = new[:block_start] + '''        const char *name = object->dir_pending_name;

        if (!name && !object->dir_scan_done)
        {
            if (object->dir_scan_index == 0) name = ".";
            else if (object->dir_scan_index == 1) name = "..";
            else
            {
                struct dirent *de;
                for (;;)
                {
                    errno = 0;
                    de = readdir( object->dir_stream );
                    if (!de)
                    {
                        if (errno) reply.header.error = horizon_server_errno_status( errno );
                        else
                        {
                            object->dir_scan_done = 1;
                            closedir( object->dir_stream );
                            object->dir_stream = NULL;
                        }
                        break;
                    }
                    if (!strcmp( de->d_name, "." ) || !strcmp( de->d_name, ".." )) continue;
                    name = de->d_name;
                    break;
                }
            }
            if (name)
            {
                object->dir_scan_index++;
                object->dir_pending_name = name;
            }
        }
        if (reply.header.error) break;
        if (!name)
        {
            reply.header.error = horizon_dir_scan_end_status( !object->dir_queried );
            break;
        }
        /* A mask change can reopen the stream, but ordinary queries never
         * replay entries already visited. Retry an unsent name in place. */
        if (object->dir_scan_index <= object->dir_enum_index ||
            !horizon_server_wildcard_match( object->dir_mask, name ))
        {
            object->dir_pending_name = NULL;
            continue;
        }

''' + new[block_end:]
    new = new.replace('        object->dir_enum_index = raw_index;',
                      '        object->dir_enum_index = object->dir_scan_index;\n        object->dir_pending_name = NULL;')
    new = new.replace('        object->dir_queried = 1;', '''        object->dir_queried = 1;
        object->dir_trace_queries++;
        trace_query = request->restart_scan || mask_changed || reply.header.error ||
                      object->dir_trace_queries <= 4 || !(object->dir_trace_queries & 255);''')
    new = new.replace('    if (dir) closedir( dir );\n', '')
    new = new.replace('    horizon_trace( "[HZDIR] query', '    if (trace_query) horizon_trace( "[HZDIR] query')
    assert new != old and 'raw_index' not in new and 'opendir( object->file_name )' in new
    text = text[:start] + new + text[end:]
    path.write_text(text)

    name2 = 'wine-nx-probe/source/runtime.c'
    runtime = source / name2
    data = runtime.read_text()
    anchor = '    pes13_fex_set_performance_profile(fex_profile);'
    assert data.count(anchor) == 1
    runtime.write_text(data.replace(anchor, anchor + '\n    wine_nx_runtime_trace("[HZDIR] v2 persistent directory cursor; bounded trace");'))
    return {name, name2}
