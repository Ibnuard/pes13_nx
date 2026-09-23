/* Only the measured, fingerprinted REP MOVSD site enables this prefix.
 * Both pointers must be 8-byte aligned: no pair crosses a protection page,
 * and positive overlaps are at least one whole pair. Odd counts, unaligned
 * pointers and DF=1 continue through the original dword loops.
 * Existing MOVS fault recovery decodes the post-index store's +8 step. */
#ifndef PES13_PERF25_COPY_EMIT_H
#define PES13_PERF25_COPY_EMIT_H
#define PES25_COPY_FORWARD() do { \
    ORRw_REG(x1, xRSI, xRDI); \
    ANDw_mask(x1, x1, 0, 2); \
    CBNZw_MARK(x1); \
    TBNZ_MARK(xRCX, 0); \
    MARK3; \
    LDRx_S9_postindex(x1, xRSI, 8); \
    STRx_S9_postindex(x1, xRDI, 8); \
    SUBx_U12(xRCX, xRCX, 2); \
    CBNZx_MARK3(xRCX); \
    B_NEXT_nocond; \
} while (0)
#endif
