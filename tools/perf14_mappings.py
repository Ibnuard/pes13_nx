"""Keep libnx reservations held throughout Horizon mapping transitions."""

def replace_once(text, old, new):
    assert text.count(old) == 1, (text.count(old), old[:120])
    return text.replace(old, new)


def patch_horizon(text):
    # Pieces may overlap the parent's libnx reservation. Retain the parent
    # until all replacements exist, including during rollback on failure.
    start = text.index('static int change_section_range(')
    end = text.index('static int protect_section_range(', start)
    part = text[start:end]
    part = replace_once(part, '    remove_reservation( mapping->reservation );\n', '')
    part = replace_once(part, '    free_section_range( mapping );\n    return 0;',
        '    remove_reservation( mapping->reservation );\n'
        '    free_section_range( mapping );\n    return 0;')
    part = replace_once(part,
        '    if (!(mapping->reservation = reserve_fixed_range( mapping_start, mapping_end - mapping_start )))\n'
        '        WARN( "lost the reservation of a view of a section at %p-%p.\\n", mapping_start, mapping_end );\n',
        '    /* PERF14: the original reservation stayed held during rollback. */\n')
    text = text[:start]+part+text[end:]

    # An anonymous reservation's metadata split releases its middle range.
    # Guard that middle until map_backing_at has installed its own reservation.
    start = text.index('static int protect_range_locked(')
    end = text.index('static int horizon_query_region(', start)
    part = text[start:end]
    part = replace_once(part, '            if (prot != PROT_NONE)\n            {\n',
        '            if (prot != PROT_NONE)\n            {\n'
        '                VirtmemReservation *transition;\n'
        '                int saved_errno;\n\n'
        '                /* PERF14: native allocators must not take the commit hole. */\n'
        '                if (!(transition = reserve_fixed_range( start, protect_size ))) return -1;\n')
    for anchor in ('split_reservation failed', 'commit map_backing failed'):
        marker = part.index(anchor)
        finish = part.index('                    return -1;', marker)
        part = part[:finish]+part[finish:].replace('                    return -1;',
            '                    saved_errno = errno;\n'
            '                    remove_reservation( transition );\n'
            '                    errno = saved_errno;\n'
            '                    return -1;', 1)
    part = replace_once(part, '            }\n        }\n        else\n',
        '                remove_reservation( transition );\n'
        '            }\n        }\n        else\n')
    text = text[:start]+part+text[end:]

    # MAP_FIXED file sections need the same handoff guard as anonymous maps.
    start = text.index('static void *horizon_mmap_section(')
    end = text.index('void *horizon_mmap(', start)
    part = text[start:end]
    part = replace_once(part, '    VirtmemReservation *reservation = NULL;',
        '    VirtmemReservation *reservation = NULL, *transition = NULL;\n    int saved_errno;')
    part = replace_once(part,
        '    if ((flags & MAP_FIXED) && (!start || unmap_range_locked( start, size )))\n'
        '    {\n        if (!start) errno = EINVAL;\n        goto failed;\n    }',
        '    if (flags & MAP_FIXED)\n'
        '    {\n'
        '        if (!start) { errno = EINVAL; goto failed; }\n'
        '        /* PERF14: cover the interval while the old map is removed. */\n'
        '        if (!(transition = reserve_fixed_range( start, size ))) goto failed;\n'
        '        if (unmap_range_locked( start, size )) goto failed;\n'
        '    }')
    part = replace_once(part, '    section_view_maps++;\n',
        '    section_view_maps++;\n    if (transition) remove_reservation( transition );\n')
    part = replace_once(part, 'failed:\n    pthread_mutex_unlock( &mapping_mutex );',
        'failed:\n    saved_errno = errno;\n'
        '    if (transition) remove_reservation( transition );\n'
        '    errno = saved_errno;\n'
        '    pthread_mutex_unlock( &mapping_mutex );')
    text = text[:start]+part+text[end:]
    return text
