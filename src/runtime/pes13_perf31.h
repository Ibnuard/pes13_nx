/* Bounded native submit diagnostics. Durations are nested wall times, not GPU time. */
#ifndef PES13_PERF31_H
#define PES13_PERF31_H
#include <stdint.h>
enum pes31_stage {
    PES31_QUEUE_LOCK, PES31_QUEUE_DRIVER, PES31_QUEUE_STATE, PES31_UPLOAD_FLUSH,
    PES31_UPLOAD_WAIT, PES31_QUEUE_WAIT, PES31_COMMANDS, PES31_SIGNAL,
    PES31_HOST_SYNC, PES31_CHANNEL_SUBMIT, PES31_CHANNEL_LOCK, PES31_ORDER_LOCK,
    PES31_RESERVE, PES31_THROTTLE, PES31_KICKOFF, PES31_AUDIO_LOCK,
    PES31_AUDIO_PUMP, PES31_AUDIO_RELEASE, PES31_SUBMIT_API, PES31_SUBMIT_CREATE,
    PES31_SUBMIT_DESTROY, PES31_SIGNAL_UNWRAP, PES31_TIMELINE_INSTALL,
    PES31_TIMELINE_GC, PES31_FENCE_QUERY, PES31_FENCE_WAIT, PES31_ERROR_SCAN, PES31_STAGES
};
enum pes31_value {
    PES31_SLM_WARP, PES31_SLM_TPC, PES31_IMAGE_POOL, PES31_SAMPLER_POOL,
    PES31_AUDIO_HELD, PES31_AUDIO_SUBMITTED, PES31_AUDIO_PLAYED, PES31_VALUES
};
struct pes31_token {
    uint64_t start, previous_start;
    uintptr_t object, previous_object;
    unsigned stage, previous_stage, slot;
};
extern struct pes31_token wine_nx_perf31_enter(unsigned stage, uintptr_t object);
extern void wine_nx_perf31_leave(struct pes31_token token);
extern void wine_nx_perf31_value(unsigned value, uint64_t data);
extern int wine_nx_perf31_poll_mode(void);
extern void wine_nx_perf31_poll_count(int deferred);
#define PES31_TIME(stage, object, statement) do { \
    struct pes31_token pes31_token = wine_nx_perf31_enter(stage, (uintptr_t)(object)); \
    statement; \
    wine_nx_perf31_leave(pes31_token); \
} while (0)
#endif
