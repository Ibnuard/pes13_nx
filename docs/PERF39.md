# PERF39: capture repair for the PERF38 hot blocks

PERF39 keeps the PERF38 gameplay path, Box64 preset, DXVK, math fusion and
quiet configuration. It changes only an opt-in diagnostic callback on completed
translations. PERF38's callback omitted blocks translated with the fallback
Box64 environment while the game preset was enabled. The latest diagnostic
log showed both hot blocks compiled but neither saved: `0x113027b` can compile
before the first present, and `0x112f8f0` is in the matrix page deliberately
excluded from the game environment. PERF39 allows these completed fallback
blocks into the same fingerprinted, bounded capture routine. No code is added
to the executed guest block or the per-frame rendering path.

Install `pes13-perf39-capture-repair.zip` at the SD root. The forwarder still
points to `switch/pes13-nx/pes13-nx.nro`. This quiet package keeps
`profile=0` and `perf17_capture=0`, so it is suitable as a PERF38-equivalent
control but should **not** be expected to raise FPS on its own.

To collect the missing evidence, install
`pes13-perf39-diagnostics-overlay.zip` **after** the main package. This overlay
contains configuration only, enabling the existing CPU sampler and block
capture. Close PES13-NX fully through HOME → X → Close, then play through
kick-off and a replay/corner or other slowdown. Keep `pes13-nx.log` before a
second run rotates it. The log marker must be
`pes13-nx-0.2.0-perf39-capture-repair`; look for `[PERF17-BLOCK] slot=6` and
`slot=7`. Captures are one-shot and limited to 16 KiB of native code per slot.
Reinstall the main package afterwards to return to quiet mode.

On the PC, analyze that log with
`python tools/analyze-perf38-diagnostics.py --build perf39 <pes13-nx.log>`.
The analyzer saves the two captured blocks and interval summaries under
`local/perf39/results/`.

The diagnostic run's sampler and log serialization can affect FPS. Compare
performance using the quiet package and the same CPU/GPU/RAM clocks and
game settings as PERF38. This revision does not claim 30 FPS, a startup-hang
fix, or a proven cause of event-triggered slow motion. The captured code and
thread samples will guide the next performance change.
