# PERF42: loading recovery experiment

The supplied PERF41 log ends in a real guest read access violation at
`pes2013.exe` EIP `0x0115c36f`, reading address `0x00000004`. The main game
process exits, so the image left on screen is the last loading frame, not an
active loading loop. Older PERF24/27/28/35 runs have shown the same fault; the
new PERF41 math option alone is not established as the cause. The supplied log
represents one attempt, although the tester reports four failed launches.

PERF28 captured the surrounding x86 code and table. The lookup for key
`0x0386` returns null, and the game immediately reads `[null+4]`. PERF42
checks the executable identity, exact fault address and registers, the
captured x86 instruction bytes, and the input cursor on the guest stack.
Only when all checks match does it continue at the loop's next-input path,
treating that absent record as empty. The recovery is limited to four times
per process. It runs after Box64 has unwound the fault; other faults retain
normal exception handling. This is a guarded experiment, not proof of the
underlying cause or a general crash suppressor.

This package starts from PERF40, which the tester reported reaching the match
and briefly reaching about 30 FPS. It excludes the additional PERF41 matrix
rounding change. Its gameplay fast-math flags, DXVK, Mesa, Box64, and game
files are otherwise the PERF40 package. `configuration.ini` adds
`perf42_startup_guard=1`. A successful intervention writes `[BOOT42]` to
`pes13-nx.log`. A run without that marker did not take this recovery path.

Install `pes13-perf42-startup-guard.zip` at the SD root, overwriting the NRO
and configuration file. Do not remove `drive_c` or the PES13 game files. Close
the app through HOME > X before each run. Try three launches and record which
reach the menu. Save each run's log before it rotates. Only after repeated
menu entry, compare match performance at the same clock settings.

To compare on the **same NRO**, install
`pes13-perf42-guard-off-overlay.zip` after the main package. This replaces
only `configuration.ini`, setting `perf42_startup_guard=0`. Restore the main
package to re-enable it. This control is useful if the guard creates an
unexpected game-side effect.
