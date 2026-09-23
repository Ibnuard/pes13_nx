/* CPU-side wall times only: asynchronous and nested spans must not be summed.
 * No GPU timestamp, no allocation, no logging or file flush on the hot path. */
#ifndef PES13_PERF27_METRICS_H
#define PES13_PERF27_METRICS_H
#include <stdint.h>
enum pes27_stage {
    PES27_PRESENT, PES27_PRESENT_LOCK, PES27_SURFACE_BEFORE, PES27_SURFACE_AFTER,
    PES27_ACQUIRE, PES27_SUBMIT, PES27_FENCE, PES27_SEMAPHORE, PES27_IDLE,
    PES27_STAGES
};
extern unsigned long long wine_nx_perf8_tick(void);
extern void wine_nx_perf27_span(unsigned int, unsigned long long);
#define PES27_TIME(stage, statement) do { \
    unsigned long long pes27_begin = wine_nx_perf8_tick(); \
    statement; \
    wine_nx_perf27_span(stage, wine_nx_perf8_tick() - pes27_begin); \
} while (0)
#endif
