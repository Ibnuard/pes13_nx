# PERF17 result: the experiment did not activate

The supplied 64,743-byte log identifies PERF17, DXVK 3.1.1, NVK 26.2.2
on Tegra X1/GM20B, and a final 1280×720 swapchain. Profiling and verbose
logging are off. Archived input: `local/perf17b/perf17-identity-rejected.log`,
SHA256 `8ce742f1333e748a8a07b0510ac557f7198c56bf3d4275803c8267de398cf758`.
Numeric summary: `local/perf17b/analysis.json`.

Every post-initialization PERF17 report has `hotblocks=1 identity=-1
selected=0 completed=0 capture=1`. There are no PERF17 block snapshots.
The package was selected, but its identity guard rejected activation.
Consequently this run tests neither the scoped BIGBLOCK optimization nor
the code-capture path. It cannot establish that those changes improve or
fail to improve performance.

| Report intervals ending | Successful presents/s, weighted | Total CPU |
| --- | ---: | ---: |
| 40–50 s, menu candidate | 54.10 | 0.71–1.18 cores |
| 80–110 s, selection candidate | 7.62 | 1.94–2.13 cores |
| 160–210 s, match candidate | 5.49 | 3.03–3.15 cores |

Scene labels are inferred from the user's sequence, not synchronized
markers. Late worker 176 uses 96–98% of one core, worker 124 uses
78.1–88.7%, and the main thread uses 82.3–86.5%. This is consistent with
the previous samples prioritizing CPU-side translated game execution.
GPU duration and queue starvation are not directly measured. Differences
from prior runs are not demonstrated optimization gains; clocks and scenes
are not fully controlled, and this experiment never activated.

The old guard read the live first 512 bytes at 0x400000 when translation
first touched a hot region, compared them with the on-disk header, and
permanently cached any failure. The log does not distinguish an unreadable
mapping from differing bytes. Packed code may rewrite headers, and a live
header is an inappropriate persistent file-version check. It is not
proven from this log that a particular field was rewritten, nor that the
user installed the wrong EXE.

PERF17B binds the actual target's on-disk header to the loader-confirmed
main image base and size immediately after mapping and before guest
execution. It logs disk and initial loaded fingerprints and distinct
failure reasons. Unknown file headers and wrong mappings remain rejected;
the guard is not simply disabled. See [PERF17B.md](PERF17B.md).

Rendering explanation: the GPU is already selected through DXVK/NVK.
[DXVK translates graphics API calls to Vulkan](https://github.com/doitsujin/dxvk);
it does not turn arbitrary game/CPU code into GPU compute kernels.
[Vulkan still requires host-side command preparation and synchronization](https://docs.vulkan.org/guide/latest/threading.html).
The main/game workers must prepare an updated scene and drawing work before
the GPU can consume it. The samples do not yet identify skinning, animation,
culling or a particular synchronization loop as the dominant routine.
The log's extended software-vertex constant-set message alone also does
not prove active CPU software rendering; see the earlier PERF15 result.
