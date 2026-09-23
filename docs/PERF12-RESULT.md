# PERF12 result: smoother 2D, severe slowdown with player models

Input: `local/perf13/perf12-2d-smooth-3d-slow.log`, 55,953 bytes,
SHA256 `a50776e0a68bba3e3e8ffc5ef1dcda4e93fdbe9582bb4f056f1c1871e32570f6`.
The user reports smooth 2D at their safe overclock, falling to roughly
3–5 FPS when player models appear in team selection. Screenshots show the
region selection and the subsequent team/lineup screen with two player models.
There is no timestamp connecting a screenshot to a particular log interval.

The NRO is still PERF11 / Box64 0.4.4. Profiling is off, and BIGBLOCK=0,
SAFEFLAGS=2, FASTNAN=0, FASTROUND=0, STRONGMEM=1, X87DOUBLE=1, CALLRET=0.
The server now receives large numbers of suspend requests, consistent with
installation of the PERF12 ARM64 ntdll. The SD DLL was not independently hashed.

| Interval ending at | Presents/second | Total CPU, cores | Thread 72 | Thread 124 | Suspend requests/interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| 60 s | 46.25 | 1.79 | 61.8% | 58.4% | 608,656 |
| 70 s | 26.93 | 2.45 | 73.2% | 77.9% | 308,759 |
| 80 s | 27.82 | 3.04 | 79.0% | 87.2% | 83,767 |
| 90 s | 5.08 | 2.83 | 84.5% | 91.8% | 319,496 |
| 100 s | 2.59 | 2.50 | 84.9% | 89.0% | 318,001 |
| 110 s | 3.00 | 2.77 | 88.4% | 94.9% | 329,427 |
| 120 s | 2.20 | 3.00 | 89.2% | 90.6% | 332,184 |
| 130 s | 2.60 | 2.75 | 90.7% | 94.9% | 338,276 |

Each interval is approximately 10 seconds. Late suspend traffic is about
32,000–34,000 requests/second. Native server request durations include waiting
and overlap across connections: neither their sum nor the `select` aggregate
is CPU time. Short `host_present_ms_per_call` is not full GPU rendering time.

The cache contains 427 shaders, and DXVK configures four compiler threads.
Neither statement proves that all shaders are warm or that the compilers are
busy in the slow scene. Threads 28/32 (DXVK entries) have intermittent activity;
the two largest sustained CPU consumers still enter through the game's
0x4da0e3 thread routine. Existing HMAP replacement failures remain in this log;
the game progresses despite them, so they are not yet established as the cause.

PERF12 fixes false-success reporting; it does not implement running-thread
suspension. The current Horizon helper returns NOT_SUPPORTED once the target
has started. The call volume and earlier suspend call-site samples make
repeated refusal a specific backoff experiment. This is not proof that the
same mechanism explains every slow frame, nor does it exclude NVK overhead.

PERF13 delays the caller for 1 ms after that specific error, then returns the
unchanged result. It still validates each request at the server, without
stale handle caches or false success. The test will determine whether reducing
this polling frees useful CPU time or instead slows game coordination.

