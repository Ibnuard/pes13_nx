/* Bounded native submit diagnostics. Durations are nested wall times, not GPU time. */
#ifndef PES13_PERF30_H
#define PES13_PERF30_H
#include <stdint.h>
enum pes30_stage {
    PES30_QUEUE_LOCK, PES30_QUEUE_DRIVER, PES30_QUEUE_STATE, PES30_UPLOAD_FLUSH,
    PES30_UPLOAD_WAIT, PES30_QUEUE_WAIT, PES30_COMMANDS, PES30_SIGNAL,
    PES30_HOST_SYNC, PES30_CHANNEL_SUBMIT, PES30_CHANNEL_LOCK, PES30_ORDER_LOCK,
    PES30_RESERVE, PES30_THROTTLE, PES30_KICKOFF, PES30_AUDIO_LOCK,
    PES30_AUDIO_PUMP, PES30_AUDIO_RELEASE, PES30_STAGES
};
enum pes30_value {
    PES30_SLM_WARP, PES30_SLM_TPC, PES30_IMAGE_POOL, PES30_SAMPLER_POOL,
    PES30_AUDIO_HELD, PES30_AUDIO_SUBMITTED, PES30_AUDIO_PLAYED, PES30_VALUES
};
struct pes30_token {
    uint64_t start, previous_start;
    uintptr_t object, previous_object;
    unsigned stage, previous_stage, slot;
};
extern struct pes30_token wine_nx_perf30_enter(unsigned stage, uintptr_t object);
extern void wine_nx_perf30_leave(struct pes30_token token);
extern void wine_nx_perf30_value(unsigned value, uint64_t data);
#define PES30_TIME(stage, object, statement) do { \
    struct pes30_token pes30_token = wine_nx_perf30_enter(stage, (uintptr_t)(object)); \
    statement; \
    wine_nx_perf30_leave(pes30_token); \
} while (0)
#endif
