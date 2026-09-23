# PERF18 result: still far from playable 3D

The 91,020-byte hardware log is archived at `local/perf19/perf18-result.log`.
SHA256: `a89448509a0e8ce2fd809a98998f93fa5e6ce9d7a6f93efe2fc46e2ca4d9b709`.
Reproduce the timing summary with `tools/analyze-perf18-result.py`.

PERF18 activated: `roundguard=1 identity=1 emitted_sites=151 matrix_sites=143`.
The matrix block's emitted native size increased from 7,064 to 9,928 bytes
because each floating operation gained a conditional guard. Its capture is
truncated at 8,192 bytes; the complete x86 bytes match the earlier capture.

The intervals ending 70–90 seconds average 9.23 successful presents/s;
those ending 140–180 seconds average 5.65/s. The latter group uses
2.76–2.85 CPU cores, with game workers 176 and 124 near one core each.
The user reports that 3D is still severely laggy. Scene labels are inferred
and clocks/scenes are not controlled across runs, so the numerical
difference versus PERF17B is not a proven optimization gain.

PERF18 still executes a control-word read, bit conversion, FPCR read and
comparison for every floating operation. The complete baseline capture
shows a straight-line matrix routine with 143 rounding groups, no calls,
no interior branches and no intervening uses of the rounding scratch
registers outside those groups. This permits a narrower experiment:
set the requested mode once and restore it once for this exact block.

PERF19 implements that experiment on generated ARM64 code. It is gated
by the image identity, exact guest and native fingerprints, block size,
absence of secondary entries and absence of CALLRET metadata. It leaves
all instruction offsets intact for existing fault/profiling metadata.
No game EXE bytes or global Compatible flags are changed.

Whole-block replay in Unicorn produces identical guest memory, guest
registers, floating register cache, FPSR, NZCV and restored FPCR in 1,728
cases. The tested body executes 703 instructions versus 1,760 before,
and two FPCR writes versus 286. These are **instruction counts**, not
Switch cycle timings or whole-game FPS gains. Other busy game routines
remain. Optional 10 ms sampling will help identify them after this change.
