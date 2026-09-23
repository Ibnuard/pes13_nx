/* CPU-side Vulkan spans. These do not measure GPU execution. */
#ifndef PES13_PERF44_METRICS_H
#define PES13_PERF44_METRICS_H
#include <stdint.h>

enum pes44_stage {
    PES44_PRESENT, PES44_PRESENT_LOCK, PES44_SURFACE_BEFORE,
    PES44_SURFACE_AFTER, PES44_ACQUIRE, PES44_SUBMIT, PES44_FENCE,
    PES44_SEMAPHORE, PES44_IDLE, PES44_STAGES
};
extern unsigned long long wine_nx_perf8_tick(void);
extern void wine_nx_perf44_span(unsigned int, unsigned long long);
#define PES44_TIME(stage, statement) do { \
    unsigned long long pes44_begin = wine_nx_perf8_tick(); \
    statement; \
    wine_nx_perf44_span(stage, wine_nx_perf8_tick() - pes44_begin); \
} while (0)
#endif
