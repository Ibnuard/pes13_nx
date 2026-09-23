# PERF9 no-spin hardware report

User confirmed the latest log is from PERF9 lock-test (no-spin).
Input SHA256: 77febfb3b8f2c0c4e7b7bf75f84676014653bf9b276111135638cf8a47ac804c.
Archived log: dist/perf8-evidence/latest-perf9-unconfirmed.log (name predates confirmation).

Sampler is off. PERF8 block policy is active. In report intervals ending at
120-220 seconds, 405 successful presents over 110230 ms = 3.674 FPS.
Intervals ending 230-290 seconds: 289 presents over 70029 ms = 4.127 FPS.
Scenes are not labelled in the log; the user reports the slowdown at 3D onset.
At 250/260/270 seconds, translation attempts are 51820/51825/51826,
while FPS remains 4.00/3.90/4.00. Persistent slowdown is therefore not explained
solely by continual new Box64 block compilation. This says nothing directly
about shader compilation; there is no shader timing in these counters.

Thread 124 remains about 98.5% of one core in the late intervals. Thread 72
is around 80-81%, but shares core 1 with thread 176 (~16-17%); the lower
percentage does not establish that no-spin reduced its work. A matched control
run is not yet available. No material fix is demonstrated, and regression
relative to older runs cannot be claimed without matched clocks/scenes.

Host vkQueuePresentKHR wall time averages 22.934 ms/call at 230-290 s,
versus ~242 ms per successful present. These are asynchronous/threaded paths;
do not subtract them to obtain CPU or GPU time. Full GPU timing is not measured.

Important follow-up: tools/build-perf3-test.py introduced an ARM64
RtlWow64SuspendThread stub which always reports success without suspending
and reports previous suspend count zero. The inherited DLL is still retained
by PERF8. Late log intervals contain ~1090 resume_thread requests per ten
seconds. Combined with earlier SuspendThread caller samples, this makes
suspend/resume semantics worth auditing before more performance presets.
It is a correctness concern, not proof of the observed slowdown. Do not fix
it by naively pausing Horizon threads: suspending a thread holding runtime
locks can deadlock the process, and proper nested suspend/resume/context
semantics are required.

No new runtime change in this report. Keep no-spin experimental; the control
ZIP restores the original x86 ntdll while retaining PERF8 NRO and sampling-off.
