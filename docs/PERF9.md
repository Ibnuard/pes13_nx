# PERF9: critical-section spin experiment

This package needs the existing PERF8 NRO. It contains NO new NRO. The log
will still identify PERF8, and its ten-second FPS/thread metrics remain available.
Hardware performance is unverified.

## Evidence and hypothesis

The CPU sampler repeatedly finds thread 72 executing PES and x86 ntdll, including
RtlEnterCriticalSection/RtlLeaveCriticalSection; the main thread also appears in
critical-section waits. Disassembly of the pinned Wine x86 DLL confirms a spin
loop before the blocking acquisition path. The profiler aggregates PCs into
32-byte buckets, so it cannot tell exactly how many samples were in the spin
instructions rather than adjacent lock-acquisition instructions. This test checks
whether spinning under translation/scheduling pressure is a material cost.

## Exact change

In x86 `drive_c/windows/syswow64/ntdll.dll`, the JE at RVA 0x5317d becomes JMP.
Both branches target RVA 0x531cf, the existing SpinCount==0 path beginning with
LOCK INC [ESI+4]. This bypasses the initial try-acquire/spin phase and uses the
normal atomic acquisition, recursive-owner check, wait and wake path.
The exported SpinCount values remain unchanged. No lock, memory barrier, wait,
wake-up, game instruction or RtlLeaveCriticalSection code is removed.

The patch modifies ONE code byte plus the PE checksum; all export addresses,
imports, file size and section layout are preserved. The packaging tool refuses
any source DLL except the recorded SHA256 and asserts the instruction bytes and
target. This is a reversible test patch to Wine, not a rebuilt game executable.
Source: the project's Wine-NX test-build-2 x86 DLL; see project licenses.

## Test

1. Close PES. Extract `switch` from `pes13-perf9-lock-test.zip` to SD root,
   overwrite, and use the existing forwarder.
2. Keep CPU/GPU/RAM fixed (prefer 1728/768/1600 MHz for the current target).
   Use the same teams, stadium and camera. Play a match for at least 60 seconds.
3. Save the log as `perf9-no-spin.log`.
4. Extract `switch` from `pes13-perf9-control.zip`, restart and repeat under the
   same conditions. Save that log as `perf9-control.log`.

Both packages disable the intrusive CPU sampler, retain verbose=0 and leave
`perf8-turbo.txt`, saves, controller data and settings.dat alone. Compare both
new runs with each other; comparing to the sampling-on run would be misleading.
Allow a warm-up in the same scene for both runs to reduce shader/cache effects.
The control ZIP restores the original x86 ntdll and also serves as rollback.

Do not expect a new PERF9 log marker: only the DLL changes. Package manifests
record hashes; verify the installed `syswow64/ntdll.dll` hash if installation is
in doubt. The ARM64 DLL in `system32` is not changed.

Possible outcome: less spinning could reduce CPU waste, or extra sleeping and
wake-up overhead could make short lock handoffs slower. No FPS gain is promised.
Repeated uncontended game loops may remain expensive even if this test helps.

## Validation and reproduction

`tests/perf9_critical_section.py` extracts the pinned Wine C entry routine and
tests original/no-spin variants on the host with a modeled wait/wake backend:
uncontended acquisition, recursive acquisition, four contending workers,
mutual exclusion and final lock state. It does not validate Horizon scheduling.

```
python3 tests/perf9_critical_section.py /home/blekjek/pes13-build/source
python tools/package-perf9-lock-test.py --ntdll <original-x86-ntdll.dll>
```
