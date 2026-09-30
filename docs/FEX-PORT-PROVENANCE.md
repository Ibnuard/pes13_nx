# FEX-Emu on Switch: FEXTendo's port and source provenance

**AndroSwitch Project / Ibnuard develops FEXTendo's Nintendo Switch port and
Horizon/Wine integration of FEX-Emu.** FEX-Emu's contributors develop the CPU
translation engine. Wine and Wine-NX / Autorun provide the Windows API,
loader and native Horizon runtime on which this integration runs.

The port's contribution is the platform adaptation: making upstream FEX's
ARM64 WOW64 module work with Horizon executable memory, calling conventions,
exceptions, clocks and constrained address space, then integrating and testing
it in the PES13 wrapper. The source and history below make that work reviewable.

## Project statement: runtime provenance and FEX port authorship

**AndroSwitch Project / Ibnuard developed FEXTendo's FEX port using upstream
FEX-Emu source as its starting point.** Wine-NX supplies runtime source and
platform references. This project developed the Switch adapter, JIT memory
mappings, ABI preservation, exception integration and guest tests. Crediting
Wine-NX for its source does not transfer authorship of our porting work to
another project.

The sequence is documented: **FEX was already running a guest on Switch on
24 September 2026. The Autorun timer backport was introduced here on
27 September.** That backport was absent from the initial implementation
that achieved the guest PASS. Subsequent comparisons with Autorun and
adaptations of its optimizations followed the working FEX port, with credit
given to each reused component.

**Any allegation that this port copied another project's FEX implementation
must identify specific code: the files, functions, source revisions and
portions allegedly copied.** Sharing FEX-Emu as a dependency, using the
Wine-NX runtime, or developing FEX support during the same period is not
sufficient evidence for that allegation. Both upstream contributions and
our porting work deserve accurate attribution. If a source or attribution
has been overlooked, identify it so it can be reviewed and corrected.

## Why LSFG was removed

Ibnuard's stated reason for removing the optional LSFG frame-generation
integration was the impact of allegations that he had stolen code for the
FEX port. He was concerned that keeping LSFG visible in the project would
lead to further accusations of code theft and extend the dispute over the
authorship of his Switch porting work. Removing that optional integration
was his response to that concern.

The earlier LSFG integration was documented as adapting Autorun and
lsfg-vk work, with credit to those upstream contributors. That attribution
remains in the repository history. The
[removal checkpoint](https://github.com/Ibnuard/pes13_nx/commit/3d61a85844ce6e293d521abfbd0956b372ec4624)
removed the launcher option, backend and associated build/package code.
The FEX port's implementation and upstream dependencies remain documented
separately below so that authorship questions can be assessed against
specific source files and commits.

## Where each part comes from

| Layer | Source and contribution |
| --- | --- |
| CPU translation and WOW64 module | [FEX-Emu at `e2f973fe`](https://github.com/FEX-Emu/FEX/tree/e2f973fe931e6dc2ce523795e51ca1ac3ca85816). FEX supplies instruction decoding, translation, its ARM64 JIT and the upstream WOW64 implementation. FEXTendo applies platform patches to these components. |
| Windows and Horizon runtime | Wine-NX at `1bc4e451`, pinned in [dependencies.json](../dependencies.json), and its Wine upstream. Wine-NX is now [Autorun](https://github.com/autorunhq/autorun). Its loader, Windows API implementation, platform services and native-to-PE callback machinery are inherited foundations. |
| Switch host adapter and integration | AndroSwitch Project / Ibnuard's adapter in [src/fex/](../src/fex/), together with the FEX and Wine integration patchers. The implementation map below identifies concrete responsibilities and tests. |
| Graphics and platform libraries | DXVK, Mesa/mesa-switch, libnx and their dependencies retain their authorship. Integrating or rebuilding them does not transfer authorship to FEXTendo. |
| Additional runtime backports | Later Autorun timer and graphics-worker changes are reused/adapted with attribution, as detailed below and in [THIRD_PARTY.md](../THIRD_PARTY.md). |

FEX's [upstream WOW64 module](https://github.com/FEX-Emu/FEX/blob/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/Source/Windows/WOW64/Module.cpp)
also acknowledges André Zwing's [Hangover](https://github.com/AndreRH/hangover)
work. That upstream design and acknowledgement remain part of FEX's provenance.

## What the Switch port implements

These are platform adapters and modifications to upstream components. The
test links identify validation code; they are not claims that every revision
or configuration has passed on hardware.

| Engineering problem | FEXTendo implementation | Validation code / record |
| --- | --- | --- |
| Horizon needs separate writable and executable views of generated code. Addresses embedded in JIT instructions must still refer to the executable view. | [horizon_jit.c](../src/fex/horizon_jit.c) manages libnx CodeMemory mappings and cache maintenance. [fex_horizon_patches.py](../tools/fex_horizon_patches.py) adapts upstream FEX emission, branch patching and code metadata to the two views. libnx's underlying CodeMemory API remains upstream. | [JIT tests](../tests/fex_jit.cpp), [mapping-generation tests](../tests/fex_alias_generation.py), [FEX1 bring-up](FEX1-BRINGUP.md). |
| Calls from an ARM64 Windows module into native Horizon code must preserve Windows' `x18` thread pointer, including when native libraries use that register. | [horizon_host.h](../src/fex/horizon_host.h) and [module_host.cpp](../src/fex/module_host.cpp) define/check the host interface; [module_host_call.S](../src/fex/module_host_call.S) preserves `x18` around PE-to-native callbacks. The reverse direction uses inherited Wine-NX callback machinery. | [ABI tests](../tests/fex_abi.py), [native JIT tests](../tests/fex_jit_native.py), [FEX2 bring-up](FEX2-BRINGUP.md). |
| Native faults must reach the Wine/FEX exception path with intact register state, including when threads fault concurrently. | [wine_bridge.c](../src/fex/wine_bridge.c), [exception_entry.S](../src/fex/exception_entry.S), [exception_isolated.S](../src/fex/exception_isolated.S), [exception_slots.h](../src/fex/exception_slots.h) and [module_exception.cpp](../src/fex/module_exception.cpp) connect the host context to the inherited exception machinery. | [Context tests](../tests/fex_context.py), [exception tests](../tests/fex_exceptions.py), [unwind tests](../tests/fex_unwind.py), [FEX3 hardware record](FEX3-RESULT.md). |
| Guest mappings, code aliases and compiler allocations compete for constrained virtual address space. | [module_memory.cpp](../src/fex/module_memory.cpp), [module_heap.cpp](../src/fex/module_heap.cpp) and the FEX patcher adapt reservations and route FEX-private allocations through the native host. This changes allocator integration; the upstream allocator libraries retain their authorship. | [Allocation tests](../tests/fex_alloc.py), [heap tests](../tests/fex_heap.py), [reservation tests](../tests/fex_reservations.py). |
| Clock instructions and CPU policies must match Horizon and the Switch CPU. | [horizon_counter.h](../src/fex/horizon_counter.h), [module_counter.cpp](../src/fex/module_counter.cpp) and [module_profile.cpp](../src/fex/module_profile.cpp) adapt counter access and select upstream FEX options for this host. | [Counter tests](../tests/fex_counter.py), [native/profile tests](../tests/fex_fast_native.py). |
| The Wine loader must initialize the FEX host bridge before guest execution; code changes and floating-point state must survive the integration. | [fex_wine_patches.py](../tools/fex_wine_patches.py) wires the backend into Wine-NX; [module_smc.cpp](../src/fex/module_smc.cpp) and [module_fpu.cpp](../src/fex/module_fpu.cpp), together with the FEX patcher, adapt invalidation and context handling. FEX's translation and Wine's loader remain upstream implementations. | [SMC tests](../tests/fex_smc.py), [FPU tests](../tests/fex_fpu_context.py), original [smoke](../src/fex/guest_smoke.c) and [stress](../src/fex/guest_stress.c) guests. |

For example, the [FEX2 bring-up record](FEX2-BRINGUP.md) documents failures
caused by a clobbered `x18`, inaccessible virtual-counter instructions and
allocator reservation sizes, followed by specific fixes and checks. This
records the engineering behind the port as well as its eventual output.

## Traceable development history

These are commits in this repository. Their dates describe this project's
recorded history; they do not establish priority over another project's work.

| Recorded date | Commit | Reviewable work |
| --- | --- | --- |
| 2026-09-23 | [057388a](https://github.com/Ibnuard/pes13_nx/commit/057388ab087f1ae6d6f860065f4eb3a9ebc426f2) | FEX/Horizon feasibility notes and WOW64 export inspection. |
| 2026-09-24 | [88b6a2f](https://github.com/Ibnuard/pes13_nx/commit/88b6a2f267ae01bc8d4f8f35fb31df865800f67a) | Initial host adapter, executable-memory bridge, callback ABI, exception bridge, build patchers and original x86 smoke guest; records the Switch guest PASS. |
| 2026-09-25 | [38a6d0c](https://github.com/Ibnuard/pes13_nx/commit/38a6d0c211b9aca8edd2bd60f488f668a17fc012) | FEX3 gameplay integration and synchronous self-suspend work. |
| 2026-09-27 | [c4ec5cb](https://github.com/Ibnuard/pes13_nx/commit/c4ec5cb2d0262841c36c6cbb5472c8a2f3ea26e3) | Runtime fixes, shader-cache path, toolchain provenance and macOS cross-tooling. Includes attributed upstream work, not only original changes. |
| 2026-09-27 | [8939d56](https://github.com/Ibnuard/pes13_nx/commit/8939d56489cea2731a62c2760445e068dfbe556d) | Stability and resident dispatcher-cache integration. |
| 2026-09-29 | [8cb6433](https://github.com/Ibnuard/pes13_nx/commit/8cb643363265330b28ed7c9b1b8a4db5581bedcf) | Later CPU-polling and renderer-selection checkpoint, including explicitly credited Autorun adaptations. |

In a checkout containing this history, reviewers can inspect the initial
implementation and its subsequent changes directly:

```sh
git show --stat 88b6a2f267ae01bc8d4f8f35fb31df865800f67a
git show 88b6a2f267ae01bc8d4f8f35fb31df865800f67a:src/fex/module_host_call.S
git log --oneline -- src/fex tools/fex_horizon_patches.py tools/fex_wine_patches.py
git log --reverse --oneline -- tools/fex_runtime_fixes.py src/runtime/fex_dxvk_core3.h
```

The [FEX2 hardware result](FEX2-RESULT.md) records a user-supplied Switch run
on 2026-09-24: the original x86 guest completed 12 checkpoints and exited
successfully. It publishes the associated artifact/log hashes and the limits
of that evidence. The [FEX3 record](FEX3-RESULT.md) includes a subsequent
concurrent stress-test PASS as well as later failures and experiments. These
are bounded integration tests, not a guarantee of game performance.

## Autorun reuse and references

Autorun / Wine-NX is a substantial runtime foundation for FEXTendo. Its credit
is not limited to inspiration. Beyond that inherited base, explicit reuse
includes:

- **Waitable timers:** [fex_runtime_fixes.py](../tools/fex_runtime_fixes.py)
  adapts code from Autorun [51f94949](https://github.com/autorunhq/autorun/commit/51f94949d738c978bfb80a5118d7ffa4cf6b98ae),
  with further cancellation, catch-up and rearm changes. The initial
  [24 September port commit](https://github.com/Ibnuard/pes13_nx/commit/88b6a2f267ae01bc8d4f8f35fb31df865800f67a)
  predates this backport. The backport file was introduced here on
  [27 September](https://github.com/Ibnuard/pes13_nx/commit/c4ec5cb2d0262841c36c6cbb5472c8a2f3ea26e3);
  it did not enable the initial guest PASS. Existing Wine timer services are
  a separate inherited runtime component.
- **Graphics-worker placement:** [fex_dxvk_core3.h](../src/runtime/fex_dxvk_core3.h)
  and its wiring adapt Autorun [c2268252](https://github.com/autorunhq/autorun/tree/c2268252a28abb5977fec8ea385b43f0e9519a5f).
- **Engineering references:** the [thread/CPU audit](AUTORUN-THREAD-CPU-AUDIT-2026-09-28.md)
  records the source studied and separates implemented changes from proposals.
  FEX-aware profiling also adapts inherited Wine-NX diagnostic machinery.

The `fex_` prefix means code participates in this backend. It is not an
authorship label for every function, patch or inherited algorithm.

## How the build records its inputs

[build-fex-module.py](../tools/build-fex-module.py) fetches or reuses the pinned
official FEX source at `e2f973fe931e6dc2ce523795e51ca1ac3ca85816` and builds its
`wow64fex` target. With `--horizon`, it applies this repository's patches and
includes the adapter from `src/fex/` in a separate source/build tree.

The [Horizon patcher](../tools/fex_horizon_patches.py) checks the FEX revision,
pinned rpmalloc revision and expected source content before applying edits.
Its `patches.json` records hashes of upstream and patched files. The module's
`build.json` records the FEX revision, adapter-source hashes and resulting
DLL hash. [build-fex-runtime.py](../tools/build-fex-runtime.py) records the
matching Wine integration, patch inputs and build outputs in
`runtime-build.json`. These receipts make source and artifact comparisons
possible; they do not replace hardware testing or upstream attribution.

The new adapter files are [MIT-licensed](../src/fex/LICENSE) where marked.
Patched FEX, Wine and other components retain their own copyright notices and
licenses. See [THIRD_PARTY.md](../THIRD_PARTY.md) for the full component ledger.
