"""FEX3 native Wine reserved-address allocation; isolated from Box64 builds."""


def apply(replace):
    name = 'dlls/ntdll/unix/horizon_mman.h'
    anchor = 'extern int horizon_munmap( void *start, size_t size );'
    replace(name, anchor, '''/* Free-address search may replace only empty host reservations. */
extern void *horizon_anon_mmap_reserved( void *start, size_t size, int prot );
''' + anchor)
    name = 'dlls/ntdll/unix/horizon.c'
    anchor = 'static void *horizon_mmap_tryfixed( void *start, size_t size, int prot, int flags, int fd, off_t offset )'
    replace(name, anchor, r'''
/* Unlike MAP_FIXED, free-area search must not discard live native mappings.
 * Wine's reserved-area list can outlive its host reservation (e.g. a failed
 * replacement). Check both mapping metadata and the kernel before changing
 * anything. Keep a transition reservation across the replacement so native
 * stacks/JIT aliases cannot take the checked address in between. */
void *horizon_anon_mmap_reserved( void *start, size_t size, int prot )
{
    struct horizon_mapping *mapping;
    VirtmemReservation *transition = NULL;
    char *cursor = start, *end;
    int ret = -1, saved_errno;

    size = page_align_size( size );
    if (!start || ((ULONG_PTR)start & 0xfff) || !size || (ULONG_PTR)start + size < (ULONG_PTR)start)
    {
        errno = EINVAL;
        return MAP_FAILED;
    }
    end = (char *)start + size;
    pthread_mutex_lock( &mapping_mutex );
    while (cursor < end && (mapping = find_overlap_mapping( cursor, end - cursor )))
    {
        if (!mapping->reservation || mapping->backing || mapping->section ||
            mapping->section_state != SECTION_NONE || mapping->prot != PROT_NONE)
        {
            errno = EEXIST;
            goto done;
        }
        cursor = (char *)mapping->addr + mapping->size;
    }
    virtmemLock();
    if (horizon_overlaps_kernel_region( start, size ) ||
        !horizon_range_unmapped( (unsigned long long)(uintptr_t)start, size, horizon_query_region, NULL ))
        errno = EEXIST;
    else
        transition = reserve_fixed_range_locked( start, size );
    virtmemUnlock();
    if (!transition) goto done;

    if (unmap_range_locked( start, size )) goto done;
    if (prot == PROT_NONE)
    {
        virtmemLock();
        ret = add_reservation_mapping_locked( start, size );
        virtmemUnlock();
    }
    else ret = map_backing_at( start, size, prot, -1, 0, MAP_PRIVATE | MAP_ANON, EINVAL );
done:
    saved_errno = errno;
    if (transition) remove_reservation( transition );
    pthread_mutex_unlock( &mapping_mutex );
    errno = saved_errno;
    return ret ? MAP_FAILED : start;
}

''' + anchor)
    name = 'dlls/ntdll/unix/virtual.c'
    anchor = 'static void *alloc_free_area_in_range( struct alloc_area *area, char *base, char *end )'
    replace(name, anchor, r'''
#ifdef __SWITCH__
/* A Linux PROT_NONE reservation is exclusive. Horizon only keeps host-side
 * metadata, so a failed replacement/native alias can invalidate that promise.
 * Do not discard a whole usable arena after one EEXIST, or use exponential
 * probes which can skip its only gap. Wine's free_ranges already exclude all
 * guest views. Only the safe reserved mapper may replace these candidates. */
static void *try_map_reserved_area_range( struct alloc_area *area, char *base, char *end )
{
    char *start, *first;
    size_t step = area->align_mask + 1;
    unsigned int conflicts = 0;

    if (base >= end || (size_t)(end - base) < area->size || !step) return NULL;
    if (area->top_down) start = ROUND_ADDR( end - area->size, area->align_mask );
    else
    {
        if ((ULONG_PTR)base + area->align_mask < (ULONG_PTR)base) return NULL;
        start = ROUND_ADDR( base + area->align_mask, area->align_mask );
    }
    first = start;
    while (start >= base && start < end && (size_t)(end - start) >= area->size)
    {
        if (horizon_anon_mmap_reserved( start, area->size, area->unix_prot ) == start)
        {
            static unsigned int reported;
            if (conflicts && reported++ < 8)
                horizon_trace( "[FEX3-VA] recovered reserved allocation first=%p chosen=%p size=0x%lx conflicts=%u",
                               first, start, (unsigned long)area->size, conflicts );
            return start;
        }
        if (errno != EEXIST) return NULL;
        ++conflicts;
        if (area->top_down)
        {
            if ((size_t)(start - base) < step) break;
            start -= step;
        }
        else
        {
            if ((size_t)(end - start) <= step) break;
            start += step;
        }
    }
    return NULL;
}
#endif

''' + anchor)
    top = '''            if (intersect_end - intersect_start >= area->size)
            {
                alloc_start = ROUND_ADDR( intersect_end - area->size, align_mask );'''
    replace(name, top, '''#ifdef __SWITCH__
            if ((result = try_map_reserved_area_range( area, intersect_start, intersect_end ))) return result;
#else
''' + top)
    replace(name, '''            end = intersect_start;
            if (end - base < area->size) return NULL;''', '''#endif
            end = intersect_start;
            if (end - base < area->size) return NULL;''')
    bottom = '''        if (intersect_end - intersect_start >= area->size)
        {
            alloc_start = ROUND_ADDR( intersect_start + align_mask, align_mask );'''
    replace(name, bottom, '''#ifdef __SWITCH__
        if ((result = try_map_reserved_area_range( area, intersect_start, intersect_end ))) return result;
#else
''' + bottom)
    replace(name, '''        base = intersect_end;
        if (end - base < area->size) return NULL;''', '''#endif
        base = intersect_end;
        if (end - base < area->size) return NULL;''')
