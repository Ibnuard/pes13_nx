# PERF31-labelled uploads: actual PERF25 runs

The ten uploaded files are archived without modification in
`local/perf32/results`. `tools/audit-perf31-result.py` records hashes, build
identity, duplicate history, thread occupancy and present intervals in
`local/perf32/analysis.json`.

There are three new runs: two long PERF25 runs and one short PERF25 launch.
The other seven files repeat those runs or previously archived PERF29/PERF30
history. **None identifies PERF31**, and no `[PERF31]`/`[POLL31]` report is
present. The PERF31 quiet ZIP contained settings only; applying it over the
PERF25 reference did not replace the NRO. The packaging was too easy to misuse.
All subsequent test variants include their NRO.

| Folder label | Current log SHA-256 | Actual build | Last report |
| --- | --- | --- | --- |
| reference25 | `7a415bf69f35bf54e470f39349f9febf6429eea27d81522f555abb3ea151f96c` | PERF25 paircopy | 320 s, 15.39 presents/s |
| quiet | `64638d55ac986b7331c02cc8c75363636a432939e8f5814e69e52ce3e8928172` | PERF25 paircopy | 300 s, 18.28 presents/s |

The user reports that the second run develops persistent slowdown and audible
echo/stutter **after five real minutes**. The corresponding log stops at five
minutes, so it cannot identify the failure mechanism or rule it out. The first
run was reported stable during the test, not proven stable indefinitely.
These uploads do not establish whether the PERF31 error-scan policy helps,
hurts or changes audio behavior, since it was not running.

In the reference-labelled run, endpoints 130–180 s report 10.69–12.29
presents/s; endpoints 250–320 s recover to 14.19–15.88. In the quiet-labelled
run, endpoints 130–230 s stay around 15.58–17.18, dip to 12.57 at 240 s and
then recover to 15.39–18.59. Scene timing was not synchronized, so these are
not comparable speed measurements of different builds. Both used the same
PERF25 code and policy. Present rate is not a measure of simulation speed or
unique displayed images.

The busy worker uses roughly 88–92% of one CPU core through long sections;
worker 124 uses roughly 78–82%. Earlier PERF28 sampling independently
attributed most busy-worker samples to translated game instructions. This
supports continued CPU-translation work. It does not prove that GPU execution,
submission waits, asset loading or audio mixing can be ignored.

Native Wine is already compiled with release optimization; the core is tuned
for Cortex-A57. The remaining Box64 `-O1` applies to the translator C code,
not to a C compiler pass over every dynamically emitted game block. Merely
changing that build flag is not evidence of a twofold gameplay speedup.
The driver line about an extended software-vertex constant set alone also
does not prove that all rendering is performed by the CPU.

## Next experiment

PERF32 uses PERF25 behavior as the comparison base. It changes the immutable
post-present game environment to permit larger translated blocks, including
overlap with existing blocks. Global/startup/DLL settings and SAFEFLAGS=2,
X87DOUBLE=1, STRONGMEM=1, CALLRET=0 remain. The native math/copy emitters,
driver, audio implementation and native synchronization stay at PERF25.

This is broader than the PERF29 experiment and removes its CALLRET=2/targeted
wake dependencies from the baseline. The user's earlier PERF29
control-sampling runs had block growth disabled. No measured gain from
PERF32 is claimed. At 15–18 presents/s, reaching 30 requires roughly a
40–50% reduction in per-frame time. An on-device kick-off measurement and
continued play after repeated events are the acceptance test, not build success.
