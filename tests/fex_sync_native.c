/* Linux scheduling fixture for the actual FEX routing adapter. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
typedef uint64_t u64;
enum { HORIZON_SERVER_OBJECT_EVENT=1, HORIZON_SERVER_OBJECT_MUTEX,
       HORIZON_SERVER_OBJECT_SEMAPHORE, HORIZON_SERVER_OBJECT_THREAD };
#define HORIZON_CURRENT_THREAD_HANDLE 0xfffffffeu
#define HORIZON_SERVER_WAIT_SLICE 200000LL
struct horizon_server_object { int type; } objects[16];
struct horizon_server_handle_entry { struct horizon_server_object *object; } handles[16];
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t horizon_server_objects_cond = PTHREAD_COND_INITIALIZER;
static unsigned horizon_server_sleepers;
int wine_nx_fex_targeted_wake = 1;
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned h)
{ return h < 16 && handles[h].object ? &handles[h] : NULL; }
static void condvarWaitTimeout(pthread_cond_t *c, pthread_mutex_t *m, uint64_t ns)
{
    struct timespec until;
    assert(ns && ns <= 20000000);
    /* Deliberately no 20ms rescue polling: a missed notification must fail. */
    assert(!clock_gettime(CLOCK_REALTIME, &until)); until.tv_sec += 5;
    assert(!pthread_cond_timedwait(c, m, &until));
}
#include "fex_sync_adapter.inc"

#define CLIENTS 8
#define ROUNDS 1000
static pthread_cond_t ack = PTHREAD_COND_INITIALIZER;
static unsigned ready, completed[CLIENTS+1], tokens[CLIENTS+1];
static void *consumer(void *p)
{
    unsigned id = (unsigned)(uintptr_t)p;
    struct pes27_interest in = {.handles={id+1}, .count=1};
    pthread_mutex_lock(&horizon_server_objects_mutex);
    ++ready; pthread_cond_broadcast(&ack);
    for (unsigned round=0; round<ROUNDS; ++round) {
        while (!tokens[id]) {
            if (id == CLIENTS) horizon_server_sleep_locked(HORIZON_SERVER_WAIT_SLICE);
            else fex_sync_select_sleep_locked(HORIZON_SERVER_WAIT_SLICE, &in);
        }
        --tokens[id]; ++completed[id]; pthread_cond_broadcast(&ack);
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    return NULL;
}
static void handoffs(int targeted)
{
    pthread_t workers[CLIENTS+1];
    wine_nx_fex_targeted_wake = targeted;
    ready=0; memset(completed, 0, sizeof(completed)); memset(tokens, 0, sizeof(tokens));
    for (unsigned i=0; i<=CLIENTS; ++i)
        assert(!pthread_create(&workers[i], NULL, consumer, (void *)(uintptr_t)i));
    pthread_mutex_lock(&horizon_server_objects_mutex);
    while (ready != CLIENTS+1) pthread_cond_wait(&ack, &horizon_server_objects_mutex);
    for (unsigned n=1; n<=ROUNDS; ++n) {
        ++tokens[CLIENTS]; /* A broad self/start gate must still be woken. */
        for (unsigned i=0; i<CLIENTS; ++i) {
            ++tokens[i]; fex_sync_signal_object_locked(&objects[i+1]);
        }
        for (unsigned i=0; i<=CLIENTS; ++i)
            while (completed[i] < n) pthread_cond_wait(&ack, &horizon_server_objects_mutex);
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    for (unsigned i=0; i<=CLIENTS; ++i) assert(!pthread_join(workers[i], NULL));
    assert(!horizon_server_sleepers && !fex_sync_router.head);
}
int main(void)
{
    for (unsigned i=0; i<16; ++i) { objects[i].type=HORIZON_SERVER_OBJECT_EVENT; handles[i].object=&objects[i]; }
    handles[10].object=&objects[1];
    assert(fex_sync_resolve(10,NULL)==fex_sync_resolve(1,NULL));
    assert(fex_sync_resolve(HORIZON_CURRENT_THREAD_HANDLE,&objects[2])==&objects[2]);
    objects[11].type=99; assert(!fex_sync_resolve(11,NULL));
    handles[12].object=NULL; assert(!fex_sync_resolve(12,NULL));
    assert(!fex_sync_resolve(99,NULL));
    handoffs(1); assert(fex_sync_router.filtered);
    const struct pes27_router before_control = fex_sync_router;
    handoffs(0);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    horizon_server_signal_changed_locked();
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    uint64_t snapshot[7]; wine_nx_fex_sync_snapshot(snapshot);
    /* Control must bypass all routing work, not only disable filtering. */
    assert(!memcmp(&before_control, &fex_sync_router, sizeof(before_control)));
    assert(snapshot[3]==snapshot[4]+snapshot[5] && snapshot[6]);
    puts("PASS FEX routing: 18,000 real adapter handoffs, targeted/control, shared self/start gates, aliases, unknown/closed handles, no polling rescue; control has zero router work");
}
