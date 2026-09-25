/* SPDX-License-Identifier: MIT
 * Native heap ownership/concurrency with the production host implementation.
 * Run under ASan/UBSan on the build host; this is not a Switch benchmark. */
#include "horizon_host.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); abort(); } } while (0)
static const struct pes13_fex_host *host;
static void *transferred[8][64];
static void log_line(const char *text) { puts(text); }

static void *worker(void *arg) {
    size_t id = (size_t)arg;
    for (size_t n = 0; n < 1000; ++n) {
        size_t size = 1 + (n * 317 + id * 13) % 32768;
        size_t alignment = (size_t)16 << (n % 9);
        unsigned char *p = host->allocate_heap(size, alignment);
        CHECK(p && ((uintptr_t)p % alignment) == 0);
        memset(p, (int)id, size);
        const struct pes13_fex_heap_header *header = (const struct pes13_fex_heap_header *)p - 1;
        CHECK(header->allocation && header->size == size);
        CHECK(p[0] == id && p[size-1] == id);
        host->release_heap(p);
    }
    for (size_t n = 0; n < 64; ++n) {
        unsigned char *p = host->allocate_heap(8192, 64);
        CHECK(p);
        memset(p, (int)id, 8192);
        transferred[id][n] = p;
    }
    return NULL;
}

int main(void) {
    host = pes13_fex_native_host();
    CHECK(host->version == 3 && host->size == 96);
    CHECK(!host->allocate_heap(UINT64_MAX, 16));
    CHECK(!host->allocate_heap(16, 24));
    host->release_heap(NULL);
    pthread_t workers[8];
    for (size_t i = 0; i < 8; ++i) CHECK(!pthread_create(&workers[i], NULL, worker, (void *)i));
    for (size_t i = 0; i < 8; ++i) CHECK(!pthread_join(workers[i], NULL));
    for (size_t i = 0; i < 8; ++i) for (size_t n = 0; n < 64; ++n) {
        unsigned char *p = transferred[i][n];
        CHECK(p[0] == i && p[8191] == i);
        host->release_heap(p);
    }
    pes13_fex_set_logger(log_line);
    pes13_fex_report_heap();
    puts("PASS native heap: 8000 concurrent operations + 512 cross-thread frees (ASan/UBSan)");
    return 0;
}
