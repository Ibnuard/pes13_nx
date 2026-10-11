/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Based on the Sleeping Dogs StartupFix: reservation bookkeeping lives in BSS,
 * never in the heap being handed to the NRO. Caller holds the virtmem lock.
 */
static VirtmemReservation *fxt_guest_reservation;
static void *fxt_find_native(size_t size) {
    if (!fxt_guest_reservation)
        fxt_guest_reservation = virtmemAddReservation((void *)UINT64_C(0x200000), UINT64_C(0xffe00000));
    if (!fxt_guest_reservation) return NULL;
    void *address = virtmemFindCodeMemory(size, 0);
    uintptr_t at = (uintptr_t)address;
    if (at < UINT64_C(0x100000000) || at >= UINT64_C(0x8000000000) ||
        size > UINT64_C(0x8000000000) - at) return NULL;
    return address;
}
