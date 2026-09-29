# FEXTendo's Switch host adapter for FEX-Emu

This directory contains AndroSwitch Project / Ibnuard's host adapter and test
programs for integrating upstream FEX-Emu with the Wine-NX / Autorun runtime
on Nintendo Switch.

FEX-Emu supplies the CPU translator, ARM64 JIT and upstream WOW64 module.
The FEX build recipe fetches that source separately and applies the platform
patches in this repository. Wine-NX supplies the native Horizon runtime and
existing Wine loader/callback machinery.

The adapter implements:

- Horizon executable-memory mappings and instruction-cache maintenance.
- A versioned host interface and PE-to-native calls that preserve `x18`.
- Exception-context integration and isolated native exception storage.
- Host clock access, private heap integration and platform profiles.
- Integration helpers for code invalidation and floating-point context.
- Original x86 smoke/stress guests and native register/JIT probes.

See the [port provenance record](../../docs/FEX-PORT-PROVENANCE.md) for the
source map, initial implementation commit, build receipts and recorded Switch
test results. [THIRD_PARTY.md](../../THIRD_PARTY.md) identifies inherited code,
direct backports and references, including Autorun contributions.

Adapter files use [MIT](LICENSE) where marked; upstream notices and the
[libnx license](libnx-LICENSE) remain intact. Changes applied to upstream
files retain the respective upstream licenses.
