#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include "../src/runtime/pes13_perf24_metrics.h"
static struct pes24_hist h;
static void *writer(void *arg)
{
    (void)arg;
    for (unsigned i=0; i<100000; ++i) pes24_add(&h, i%1000);
    return NULL;
}
int main(void)
{
    for (unsigned i=0; i<PES24_BUCKETS-1; ++i) {
        assert(pes24_bucket(pes24_limits_us[i])==i);
        assert(pes24_bucket(pes24_limits_us[i]+1)==i+1);
    }
    assert(pes24_bucket(UINT64_MAX)==PES24_BUCKETS-1);
    assert(!pes24_sample_window(0));
    assert(!pes24_sample_window(7999999999ull));
    assert(pes24_sample_window(8000000000ull));
    assert(pes24_sample_window(9999999999ull));
    assert(!pes24_sample_window(10000000000ull));
    assert(pes24_sample_window(18000000000ull));
    pthread_t threads[4];
    for (unsigned i=0; i<4; ++i) assert(!pthread_create(&threads[i],NULL,writer,NULL));
    for (unsigned i=0; i<4; ++i) assert(!pthread_join(threads[i],NULL));
    struct pes24_snapshot last={0}, d=pes24_delta(&h,&last);
    assert(d.count[0]==400000 && d.total_us==199800000 && d.maximum_us==999);
    d=pes24_delta(&h,&last);
    assert(!d.count[0] && !d.total_us && d.maximum_us==999);
    pes24_add(&h,3000000);
    d=pes24_delta(&h,&last);
    assert(d.count[9]==1 && d.total_us==3000000 && d.maximum_us==3000000);
    puts("PERF24 bucket boundaries, cadence, concurrent totals and deltas PASS");
    return 0;
}
