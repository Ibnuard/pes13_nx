/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Keep the libnx reservation allocator alive across NRO handoffs/reloads.
 */
void __libnx_initheap(void) {
    extern char *fake_heap_start, *fake_heap_end;
    static char fxt_bookkeeping[16 * 1024] __attribute__((aligned(16)));
    fake_heap_start = fxt_bookkeeping;
    fake_heap_end = fxt_bookkeeping + sizeof(fxt_bookkeeping);
}
