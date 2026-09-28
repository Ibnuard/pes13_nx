/* LGPL-2.1-or-later. Best-effort JIT statistics only, never fault/lifecycle
 * records. Producers never wait for the logger or perform file I/O. */
#ifndef PES13_FEX_JIT_LOG_QUEUE_H
#define PES13_FEX_JIT_LOG_QUEUE_H
#include <pthread.h>
#include <stdint.h>
#include <string.h>

#define FEX_JITLOG_SLOTS 32
#define FEX_JITLOG_BYTES 512
static struct {
    pthread_mutex_t mutex;
    unsigned head, count;
    char lines[FEX_JITLOG_SLOTS][FEX_JITLOG_BYTES];
    uint64_t queued, written, dropped;
} fex_jitlog = {.mutex = PTHREAD_MUTEX_INITIALIZER};

static int fex_jitlog_enqueue(const char *line)
{
    static const char *const prefixes[] = {
        "[FEX3-JIT] phase=dispatch_compile ",
        "[FEX3-JIT] phase=compile_code ",
        "[FEX3-JIT] phase=invalidate "
    };
    unsigned i;
    size_t size;
    for (i = 0; i < sizeof(prefixes)/sizeof(prefixes[0]); ++i)
        if (!strncmp(line, prefixes[i], strlen(prefixes[i]))) break;
    if (i == sizeof(prefixes)/sizeof(prefixes[0])) return 0;
    size = strnlen(line, FEX_JITLOG_BYTES);
    if (size == FEX_JITLOG_BYTES) return 0; /* unexpected record: preserve original path */
    if (pthread_mutex_trylock(&fex_jitlog.mutex)) {
        __atomic_add_fetch(&fex_jitlog.dropped, 1, __ATOMIC_RELAXED);
        return 1;
    }
    if (fex_jitlog.count == FEX_JITLOG_SLOTS) {
        __atomic_add_fetch(&fex_jitlog.dropped, 1, __ATOMIC_RELAXED);
    } else {
        unsigned slot = (fex_jitlog.head + fex_jitlog.count) % FEX_JITLOG_SLOTS;
        memcpy(fex_jitlog.lines[slot], line, size + 1);
        ++fex_jitlog.count;
        __atomic_add_fetch(&fex_jitlog.queued, 1, __ATOMIC_RELAXED);
    }
    pthread_mutex_unlock(&fex_jitlog.mutex);
    return 1;
}

static int fex_jitlog_pop(char out[FEX_JITLOG_BYTES])
{
    if (pthread_mutex_trylock(&fex_jitlog.mutex)) return 0;
    if (!fex_jitlog.count) {
        pthread_mutex_unlock(&fex_jitlog.mutex);
        return 0;
    }
    memcpy(out, fex_jitlog.lines[fex_jitlog.head], FEX_JITLOG_BYTES);
    fex_jitlog.head = (fex_jitlog.head + 1) % FEX_JITLOG_SLOTS;
    --fex_jitlog.count;
    pthread_mutex_unlock(&fex_jitlog.mutex);
    return 1;
}
#endif
