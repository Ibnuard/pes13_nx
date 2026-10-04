# HIGH transition freeze: targeted diagnostic preview

This preview instruments the keyboard-v4 production runtime with the current
input/settings preview. It does not rebuild the experimental FEX adapter or
replace guest DLLs, game data, graphics presets, DXVK, or the forwarder.
The production runtime lock remains unchanged. No HIGH fix or replay-only
frame limiter is claimed. Hardware reproduction is still required.

## Evidence from the submitted transition log

The earlier analysis of `Pictures/pesnx/SS/transition.log` recorded HIGH
(`preset=3`) and Default DXVK (`renderer=0`). The sampled presentation rate
was about 53.6 successful presents/s from 64.6 to 97.2 seconds. The last
successful present was around 101.669 seconds; the count remained at 4,338
through the final sample at 105.360 seconds. No Present error was counted,
and the input-blocked flag stayed zero.

This shows an abrupt cessation of presentation. It does not identify whether
the game exited/raised an exception, a driver call stalled, or allocation
failed. It is not evidence that the controller shortcut caused this freeze.

The last allocator free count was about 127.36 MiB. That counter does not
include unclaimed allocator arena capacity, and it does not describe the
largest usable contiguous allocation. It therefore cannot establish or
exclude out-of-memory by itself. The original log is no longer at the
submitted path when this preview is packaged; these are the observations
retained from the earlier read, not a new raw-log archive.

## New evidence

- The log begins with `TRACE_V2`. Existing 2-second presentation samples remain.
- `MEM`: heap capacity, arena, allocator free space, unclaimed arena capacity,
  their sum, and allocator top free space. These are not GPU VRAM or guest VA
  availability estimates. `top_free` is not the largest free allocation.
- `STAGE`: cumulative completed calls, negative Vulkan results, and largest
  observed call duration. Durations include scheduling time, not only GPU work.
- `INFLIGHT`: native call stage, thread handle, age and limited context.
  Repeatedly increasing age is useful evidence; one normal in-flight sample
  is not proof of deadlock.
- `EVENT`: 1 = guest process termination request (including successful exit),
  2 = unhandled native exception about to park, 3 = observed native allocator
  failure, 4 = section-map failure, 5 = negative Vulkan result. For exceptions,
  `detail` is the PC and `address` is the fault address. For Vulkan errors,
  `detail` is the stage index and `address` contains stage-specific context.
- `TEXT`: last 2 KiB of native/guest standard-stream output between worker
  samples; control characters are escaped. Other production logging remains
  disabled, so a quiet text tail does not rule out a guest error.

There are 34 wrappers over 17 Vulkan entry points, covering acquire/present,
submit, fence/semaphore waits, pipeline creation, memory/resource creation,
and queue/device idle. Wrappers preserve the original arguments and result.
An exit incident is recorded before registry flushing can block. Native
allocator wrappers preserve return values, errno, and zero-size semantics;
they cannot observe every guest heap/VA failure or every libc-internal call.

Producers use fixed memory and a non-blocking try-lock. Contention drops
evidence rather than waiting; the dropped count is included. They never write
storage. The existing maintenance worker flushes the summary every two seconds,
starting after the first game presentation, for at most 600 samples. The
observer adds overhead while enabled and is not a performance benchmark.

The worker cannot guarantee a final record if the whole process/OS stops or
the app is force-closed. It is not a crash dump or GPU validation layer.

## Reproduce

1. Close the game via HOME > X > Close.
2. Copy the package's `switch` directory onto the microSD root and replace the
   NRO. The included `launcher/diagnostics.txt` enables this diagnostic run.
3. Keep the same clock settings, HIGH and Default DXVK for the first test.
   Play until the transition that previously froze.
4. If the image freezes while HOME still responds, allow roughly 10–15 seconds
   before closing so the worker can record the in-flight state. If the system
   closes the application itself, collect the log directly.
5. Copy `switch/pes13-fex/transition.log` before the next launch. Also retain
   `transition.previous.log` if testing twice. Note the last event and whether
   the application closed itself or was closed through HOME.

The package is an overlay, not a full installation. It includes no replacement
settings.dat, save, renderer DLL, or forwarder. To turn off tracing, remove
`switch/pes13-fex/launcher/diagnostics.txt`. The rollback folder contains the
previous input/settings preview NRO; it is not part of the installation copy.

## Build and verification

`tools/build-fextendo-input-fix.py --transition-trace` restores the hash-pinned
keyboard-v4 generated source before applying the observer delta. The local
WSL native-library environment still differs from the macOS production build;
the recorded dependency diff remains part of this preview's evidence.

Tests exercise bounded buffers and contention, allocator semantics, disabled
logging, 600-sample worker shutdown, escaped output, and the actual linked
ARM64 observer. Removing the Vulkan wrappers reproduces the frozen Vulkan
source after newline normalization. Existing linked ARM64 controller,
keyboard, overlay delivery, and silent-production checks are retained.
Host/ARM64 simulation success does not establish a console HIGH fix.
