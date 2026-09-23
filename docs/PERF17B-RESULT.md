# PERF17B hardware result and PERF18 motivation

Input: `local/perf18/perf17b-result.log`, 89,672 bytes, SHA256
`905fa89917bc8c8dbb33c2c480a10f6a22a0efdda4a1c01635787e22517ee970`.
Reproduce the summary with `python tools/analyze-perf17b-result.py` and
decode with `tools/decode-perf17.py`. No game files are modified.

## Activation and performance

The file identity fix works: both disk and initial mapped header have
fingerprint `4e46d440`, `identity=1`. At 210 seconds PERF17 reports
`selected=304 completed=304`. These are compilation counts, not execution
counts. Five bounded snapshots were captured. Thus this run did activate
the experiment, unlike the previous PERF17 run.

The user reports no perceptible 3D improvement. Successful presents in the
intervals ending 80–100 seconds average 6.23/s, and those ending 160–210
seconds average 4.29/s. The last group uses 2.81–2.88 CPU cores. Its main
thread uses 63.0–67.2% of a core, worker 124 uses 82.4–90.4%, and worker
176 uses 92.4–94.6%. Scene labels follow the reported sequence and are not
synchronized markers. Comparing these numbers with previous runs is not a
controlled regression measurement: clocks, scenes and timing may differ.

Host present calls in the last group average 0.263–0.788 ms each, compared
with 222–239 ms between presents. This is time inside the host-present
function, not total driver time or measured GPU duration. It cannot rule
out other driver work. Previous sampling still favors translated game work.

## Captured code

The complete 656-byte guest block at `0x112fb90` contains straight-line
x87 multiply/add operations over 4-by-4 float arrays and stores 16 outputs.
This identifies matrix arithmetic, not its higher-level purpose. We cannot
yet label it specifically as skinning, animation, or physics.

Its 7,064-byte ARM64 translation contains **143 FPCR reads and 286 FPCR
writes**: each arithmetic/conversion group installs the x87 rounding mode
and then restores the host mode. These are static instruction counts per
block traversal, not measured percentages of CPU time. The FPCR writes
are redundant whenever requested and current rounding modes already agree.

The large matrix block was compiled before the first present and is still
`bigblock=0`; PERF17 did not forcibly invalidate it. The later `bigblock=1`
capture at `0x112fb40` is a different 70-byte routine, so comparing their
sizes would be invalid. The worker snapshots also contain FPCR setup and
restoration around simple float stores.

## Next experiment

PERF18 guards the two FPCR writes for captured arithmetic/store sites.
It compares the original and requested FPCR, skips writes only if equal,
and performs the same set/restore when different. All global Compatible
options, including FASTROUND=0 and X87DOUBLE=1, remain unchanged. It acts
on the first compilation, without a first-present gate. PERF17 BIGBLOCK
is disabled to isolate the new change. See [PERF18.md](PERF18.md).

The marker used by the private generated-code helper is in bit 63 of a
scratch general-purpose register; it is cleared before any FPCR write.
FPCR's upper half is reserved on this architecture; see
[Arm's architecture reference, FPCR](https://documentation-service.arm.com/static/62015c6c965f7d118e3f5f4c).
Only paired arithmetic/store emitters use the private token; SSE and
transcendental/C-helper call paths retain the original helpers.
