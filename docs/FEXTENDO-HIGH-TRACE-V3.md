# HIGH: simulation thread stops while presentation continues

## Reproduction and retained evidence

The user reproduced the HIGH freeze with Default DXVK, around five minutes
after launch. Players/the match overlay stopped updating, while spectators
continued moving until the user closed the application. HIGH has also been
reported to fail with GPL Async; this log only identifies renderer 0.

Both submitted files are archived locally under
`local/high-freeze-review/4d0fb7dce833/`. The current log SHA-256 begins
`4d0fb7dce833`; the prior log is the older v1 reproduction, not a second v2 run.

The current 166-sample log has two recorded incidents:

| Approximate time from trace start | Evidence |
| --- | --- |
| 111.348 s | Native `memalign` returned null for 6,225,920 bytes, on thread `81ff`. The game continued presenting afterward. |
| 319.915 s | Unhandled native breakpoint `0x80000003` on thread `5f8185`, PC `0xff68bb88`. This handler parks the thread. |

From 322.462 to 341.072 seconds, presentation continues at about **59.48
successful presents/s**, with frame ages at most 15 ms in those samples.
No negative Vulkan result or Present error is recorded. Input remains unblocked.
This presentation rate is not proof that match simulation still advances.
It fits a stopped gameplay thread with a still-running renderer.

At the end, allocator free plus unused arena capacity is about 154.8 MiB.
The earlier allocation failure shows that total free space alone does not
guarantee a particular aligned contiguous allocation can succeed. The two
incidents are separated by more than three minutes; causality is not proven.

## Symbol investigation

The frozen production `libwow64fex.dll` has SHA-256
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.
Scanning the supplied ARM64 system32 DLLs for a BRK instruction at the
observed PC's 64-KiB-relative offset yields a candidate in that DLL:

- Assumed load base: `0xff540000`.
- RVA: `0x14bb88`, instruction `brk #1`.
- COFF symbol: `(anonymous namespace)::Stop(char const*) + 8`.
- Source: frozen `src/fex/module_memory.cpp`.
- The function logs a message then traps. Runtime callers include
  `PES13FexHeapFailure`, for compiler scratch, lookup or call/return-stack
  reservations/commits. Startup preflight failures also share this helper.

**The v2 log lacks the actual module base, caller and fatal message.** This
is a strong candidate under the unchanged production-DLL/32-bit-forwarder
assumption, not a verified identification of the allocation that failed.
The next trace records the base to resolve ASLR without guessing.

The production `wine_nx_runtime_trace` function discarded the FEX fatal
message and register dump. Capturing ordinary stdout/stderr in v2 did not
capture this separate callback. Also, FEX scratch uses `aligned_alloc`,
which the original four allocation wrappers did not directly cover.

## Targeted v3 changes

- Retain only FEX failure/STOP messages and unhandled exception context from
  the runtime callback. Routine tracing stays suppressed.
- Use a separate fixed queue: at most 12 records of 512 bytes per worker
  sample. Standard-stream traffic cannot overwrite these records. Messages
  include the producing thread and time, and are escaped before writing.
- Record the actual FEX DLL base and size during native bootstrap; print once
  when diagnostics start. No loader lock is taken from an exception callback.
- Record ESR, LR and SP beside the existing exception event.
- Observe `aligned_alloc` failures, retaining alignment for both aligned
  allocation APIs. Preserve the real allocator's return value and errno.
- Keep the previous bounded Vulkan, memory and presentation observers.

There is no skipped breakpoint, ignored allocation failure, arbitrary buffer
resize, replay cap, preset change, DLL rebuild, or FEX configuration change.
We need the failing operation before choosing a memory-management correction.
This is a diagnostic overlay, not a confirmed HIGH fix.

## Test and collect

Close PES. Copy the package's `switch` folder to the microSD root, replacing
the NRO and diagnostic marker. Use HIGH, Default DXVK and the same clocks.
Trigger the previously failing ball-out/replay/transition. When players freeze
but spectators move, wait 10–15 seconds then close through HOME.

Copy `switch/pes13-fex/transition.log` before relaunching. Its first line must
say `TRACE_V3`; the important new lines are `MODULE`, `FAILMSG` and exception
events. Keep `transition.previous.log` if there is another reproduction.

Remove `launcher/diagnostics.txt` to disable logging. The `rollback/switch`
folder restores the previously tested v2 NRO. No ZIP, game/save/settings.dat,
DXVK DLL, FEX DLL or forwarder is included in the installation overlay.

Host ASan/UBSan and actual ARM64 instruction tests cover filtering, bounded
failure records, aligned-allocation semantics, module metadata and disabled
logging. The native Vulkan-call integrity checks remain. These checks do not
run PES or certify the hardware fix. The frozen production source is restored
before the instrumentation patch; the release runtime lock remains unchanged.
