# PERF12 — actual suspend status experiment

The sampled PERF11 loading run shows repeated SuspendThread callers:
kernelbase+0x62473 is immediately after its NtSuspendThread import call.
Guest thread 72 spends about 92% of samples in x86 (mostly executable and
critical-section routines); thread 124 spends ~52% x86 and ~43% native,
including engine entry, memset and memcpy. The sampled DXVK thread spends
~93% in NtWaitForAlertByThreadId. Samples include blocked time and are
perturbed by profiling; these are not percentages of total process CPU.

The old ARM64 RtlWow64SuspendThread replacement always returns success and
count zero without checking the handle or changing a thread. This can mislead
code that uses suspension to coordinate workers. The sampling makes this a
specific test candidate but does not prove it causes the stuck loading.

This test forwards RtlWow64SuspendThread directly to native NtSuspendThread,
which calls the existing Horizon server. It preserves supported CREATE_SUSPENDED
start gates, nested counts and native error propagation. Already-running
thread suspension remains unsupported and returns an error, rather than fake
success. It does not implement asynchronous suspension or a cooperative stop
point and does not guarantee games tolerate that error. It adds a server call
where PERF3 skipped one, so performance may decrease or game startup may fail.

## Install

Close PES via HOME -> X -> Close. Extract **pes13-perf12-suspend-status.zip**
to the SD root and overwrite. It changes ARM64 system32/ntdll.dll, disables
sampling/verbose, and keeps the fixed-Compatible BIGBLOCK=0 policy. The NRO
still identifies as PERF11. No DXVK, x86 ntdll, game, controller, save or
settings.dat replacement is included. Keep clock/settings identical.

Test loading first. Save pes13-nx.log before reopening; if the next run works,
save that separately as well. Expect suspend_thread in the low-rate SERVER
statistics when the path is used. A new error dialog is useful evidence too.
Return with **pes13-perf12-rollback.zip** if loading regresses; it restores the
historical fake-success function, rebuilt from tools/build-perf3-test.py, and
leaves sampling off / fixed-Compatible on. The old extracted distribution has
been cleaned; this is not a byte-identical copy of the historical DLL. Back up
the current system32/ntdll.dll before the test if an exact rollback is needed.

Package checks: ARM64 PE architecture, export-name/ordinal compatibility,
direct/delay import names, ZIP CRC and file hashes.
The linked instruction at RtlWow64SuspendThread is verified to branch directly
to the same DLL's native NtSuspendThread export, rather than to itself.
The native thread state helper's existing host tests cover start gates,
nested counts, refusal of running suspension and terminated threads.
None of these checks establishes in-game correctness on Switch.
