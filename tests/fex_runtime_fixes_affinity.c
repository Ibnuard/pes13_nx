/* Real horizon_server_follow_client + lowest_set_core, mocked svc only. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef uintptr_t ULONG_PTR;
typedef uint32_t Result;
#define CUR_THREAD_HANDLE 0xffff8000u
#define R_SUCCEEDED(rc) ((rc) == 0)
struct horizon_pipe { unsigned int client_cores; };
struct horizon_server_connection {
    struct horizon_pipe *request_pipe;
    unsigned int core_mask;
};
static unsigned calls, last_mask;
static int last_preferred;
static Result next_result;
static struct horizon_server_connection *observed;
static unsigned expected_cached;
static Result svcSetThreadCoreMask(unsigned handle, int preferred, unsigned mask)
{
    assert(handle == CUR_THREAD_HANDLE);
    assert(observed->core_mask == expected_cached); /* Never cache pre-svc. */
    ++calls;
    last_preferred = preferred;
    last_mask = mask;
    return next_result;
}
#include "fex_runtime_fixes_source.inc"

int main(void)
{
    struct horizon_pipe pipe = {4};
    struct horizon_server_connection connection = {NULL, 1};
    observed = &connection;
    expected_cached = 1;
    horizon_server_follow_client(&connection);
    assert(!calls && connection.core_mask == 1);
    connection.request_pipe = &pipe;
    pipe.client_cores = 0;
    horizon_server_follow_client(&connection);
    assert(!calls && connection.core_mask == 1);
    pipe.client_cores = 1;
    horizon_server_follow_client(&connection);
    assert(!calls);

    pipe.client_cores = 6;
    next_result = 0x1234;
    horizon_server_follow_client(&connection);
    assert(calls == 1 && connection.core_mask == 1);
    assert(last_mask == 6 && last_preferred == 1);
    /* Same requested mask must retry after failure, repeatedly. */
    horizon_server_follow_client(&connection);
    assert(calls == 2 && connection.core_mask == 1);
    next_result = 0;
    horizon_server_follow_client(&connection);
    assert(calls == 3 && connection.core_mask == 6);
    expected_cached = 6;
    horizon_server_follow_client(&connection);
    assert(calls == 3); /* Success skips redundant svc. */

    pipe.client_cores = 4;
    next_result = 0x80000000u;
    horizon_server_follow_client(&connection);
    assert(calls == 4 && connection.core_mask == 6);
    next_result = 0;
    horizon_server_follow_client(&connection);
    assert(calls == 5 && connection.core_mask == 4);
    assert(last_mask == 4 && last_preferred == 2);
    puts("PASS affinity: failure preserves cache, unchanged request retries, success caches, zero/no-pipe skip");
    return 0;
}
