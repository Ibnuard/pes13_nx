/* SPDX-License-Identifier: MIT
 * rpmalloc geometry for the shared 32-bit Horizon address space.
 * Keep at least two maximum-sized blocks per allocator page. Requests above
 * the pooled limit use rpmalloc's existing direct (PAGE_HUGE) allocation.
 */
#ifndef PES13_FEX_HORIZON_HEAP_H
#define PES13_FEX_HORIZON_HEAP_H

#define PES13_FEX_HEAP_SPAN_SIZE (8 * 1024 * 1024)
#define PES13_FEX_HEAP_MEDIUM_PAGE_SHIFT 20
#define PES13_FEX_HEAP_LARGE_PAGE_SHIFT 23
#define PES13_FEX_HEAP_LARGE_BLOCK_LIMIT (2 * 1024 * 1024)
#define PES13_FEX_HEAP_LARGE_CLASS_COUNT 12

#endif
