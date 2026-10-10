"""Map shared-section anchors across free VA holes without copying their pages.

Physical backing can be contiguous even when the 32-bit address space is not.
Only a clean address-search miss permits splitting: metadata and kernel mapping
errors retain their existing failure/cleanup path.
"""


def apply(source):
    changed = set()

    def edit(name, replacements):
        path = source / name
        data = path.read_text()
        for old, new in replacements:
            assert data.count(old) == 1, (name, old, data.count(old))
            data = data.replace(old, new)
        path.write_text(data)
        changed.add(name)

    edit('dlls/ntdll/unix/horizon_memfile.h', [
        ('#define __WINE_HORIZON_MEMFILE_H', '''#define __WINE_HORIZON_MEMFILE_H
#define HORIZON_MEMFILE_SPLIT_ANCHORS 1
#ifndef HORIZON_MEMFILE_SPLIT_TRACE
#define HORIZON_MEMFILE_SPLIT_TRACE(bytes, pieces) ((void)0)
#endif'''),
        ('     * address; returns it and a token for unanchor, or NULL with errno set. */',
         '''     * address; returns it and a token for unanchor, or NULL with errno set.
     * EADDRNOTAVAIL means only address selection failed, before any reservation
     * or kernel mapping was made; the caller may retry a smaller prefix. */'''),
        ('    size_t page = first;\n\n    while (page < end)\n    {\n        size_t stop, available;',
         '''    size_t page = first, ceiling = end - first, pieces = 0;
    int split = 0;

    while (page < end)
    {
        size_t stop, available;'''),
        ('''        anchor->count = stop - page;
        if (!(anchor->addr = file->ops->anchor( source, anchor->count * page_size,
                                                &anchor->token )))
        {
            free( anchor );
            return -1;
        }''', '''        anchor->count = stop - page;
        if (anchor->count > ceiling) anchor->count = ceiling;
        while (!(anchor->addr = file->ops->anchor( source, anchor->count * page_size,
                                                   &anchor->token )))
        {
            if (errno != EADDRNOTAVAIL || anchor->count == 1)
            {
                if (errno == EADDRNOTAVAIL) errno = ENOMEM;
                free( anchor );
                return -1;
            }
            /* Never retry a kernel/metadata error: those have different
             * ownership rules. A pure VA miss is safe to divide down to one
             * page. Keep the successful ceiling for the rest of this range. */
            ceiling = anchor->count /= 2;
            split = 1;
        }'''),
        ('''        next = &anchor->next;
        page = stop;
    }
    return 0;
}

/* Maps (or unmaps)''', '''        next = &anchor->next;
        page += anchor->count;
        pieces++;
    }
    if (split) HORIZON_MEMFILE_SPLIT_TRACE((end - first) * page_size, pieces);
    return 0;
}

/* Maps (or unmaps)'''),
    ])
    edit('dlls/ntdll/unix/horizon.c', [
        ('#include "horizon_memfile.h"', '''static void horizon_section_anchor_recovered(size_t bytes, size_t pieces);
#define HORIZON_MEMFILE_SPLIT_TRACE(bytes, pieces) horizon_section_anchor_recovered(bytes, pieces)
#include "horizon_memfile.h"'''),
        ('/* The first failures of the kernel side of section views, in the runtime log. */',
         '''/* Bounded debug evidence only; normal production's trace callback is silent. */
static void horizon_section_anchor_recovered(size_t bytes, size_t pieces)
{
    static unsigned reports;
    char line[160];
    if (++reports > 16) return;
    snprintf(line, sizeof(line), "[SECTION-ANCHOR] v1 recovered bytes=%zu pieces=%zu shared_pages=1", bytes, pieces);
    wine_nx_runtime_trace(line);
}

/* The first failures of the kernel side of section views, in the runtime log. */'''),
        ('''    if (!reservation)
    {
        section_failure( "anchor address", addr, source, size, ENOMEM );''',
         '''    if (!addr)
    {
        /* Nothing is reserved or mapped. Let the shared-section layer use
         * smaller anchors while keeping the guest view contiguous. */
        errno = EADDRNOTAVAIL;
        return NULL;
    }
    if (!reservation)
    {
        section_failure( "anchor address", addr, source, size, ENOMEM );'''),
    ])
    return changed
