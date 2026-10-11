/* LGPL-2.1-or-later. mapping_mutex is held by the caller. Keep the original
 * reservation until all replacement metadata and backing pages are ready.
 * A failed commit must leave a retryable reserved range, including its libnx
 * exclusion. No guest pages or live mappings are discarded for recovery. */
static struct horizon_mapping *horizon_commit_piece(void *addr, size_t size)
{
    VirtmemReservation *r = reserve_fixed_range(addr, size);
    struct horizon_mapping *m;
    if (!r) return NULL;
    m = alloc_mapping(addr, size, NULL, 0, r, PROT_NONE);
    if (!m) { remove_reservation(r); errno = ENOMEM; }
    return m;
}

static void horizon_commit_discard_piece(struct horizon_mapping *m)
{
    if (!m) return;
    remove_reservation(m->reservation);
    horizon_object_free(&mapping_pool, m);
}

static int commit_reservation_mapping(struct horizon_mapping *original,
                                      char *start, size_t size, int prot)
{
    char *lo = original->addr, *hi = lo + original->size, *end = start + size;
    struct horizon_mapping *left = NULL, *right = NULL, *middle = NULL;
    struct horizon_backing *backing = NULL;
    int saved;

    if (lo < start && !(left = horizon_commit_piece(lo, start - lo))) goto failed;
    if (end < hi && !(right = horizon_commit_piece(end, hi - end))) goto failed;
    /* The mapping lock protects backing storage; the original reservation
     * already protects the destination from native allocators. */
    backing = create_backing_locked(size, prot, -1, 0, MAP_PRIVATE | MAP_ANON);
    if (!backing) goto failed;
    backing->code_addr = start;
    backing->code_reservation = reserve_fixed_range(start, size);
    if (!backing->code_reservation) goto failed;
    middle = alloc_mapping(start, size, backing, 0, NULL, prot);
    if (!middle) { errno = ENOMEM; goto failed; }
    if (horizon_backing_map(backing, start, 0, size, prot, EINVAL)) goto failed;

    list_remove_mapping(original);
    if (left) list_add_mapping(left);
    if (right) list_add_mapping(right);
    list_add_mapping(middle);
    remove_reservation(original->reservation);
    horizon_object_free(&mapping_pool, original);
    return 0;

failed:
    saved = errno;
    if (middle) horizon_object_free(&mapping_pool, middle);
    /* destroy_backing refuses poisoned storage if a kernel rollback failed.
     * Keep the original exclusion even in that exceptional case. */
    if (backing) destroy_backing(backing);
    horizon_commit_discard_piece(left);
    horizon_commit_discard_piece(right);
    errno = saved;
    horizon_memory_failure(5, start, NULL, size, 0);
    errno = saved;
    return -1;
}
