"""Size decoder scratch for the effective block limit, not 65,536 instructions.

IR storage, JIT limits, optimization and instruction semantics are unchanged.
The explicit loop guard also bounds speculative/invalid-instruction paths in
release builds. Grow only between compilations, before publishing any pointers.
"""


def apply(source):
    changed = set()

    def edit(name, replacements):
        path = source / name
        data = path.read_text()
        for old, new in replacements:
            assert data.count(old) == 1, (name, old[:80], data.count(old))
            data = data.replace(old, new)
        path.write_text(data)
        changed.add(name)

    edit('FEXCore/Source/Interface/Core/Frontend.h', [
        ('  size_t DecodedSize {};',
         '  size_t DecodedSize {};\n'
         '  size_t DecodedCapacity {}; // Set before claiming a compilation buffer.')])
    edit('FEXCore/Source/Interface/Core/Frontend.cpp', [
        ('PoolObject {CTX->FrontendAllocator, sizeof(FEXCore::X86Tables::DecodedInst) * DefaultDecodedBufferSize}',
         'PoolObject {CTX->FrontendAllocator, sizeof(FEXCore::X86Tables::DecodedInst)}'),
        ('  DecodedBuffer = PoolObject.ReownOrClaimBuffer();',
         '  // The decoder already stops at MaxInst. Avoid physically backing the\n'
         '  // full 65,536-entry array for a 128-instruction compilation on Horizon.\n'
         '  // Request growth here, before any block holds pointers into the array.\n'
         '  DecodedCapacity = std::clamp<uint64_t>(MaxInst, 1, DefaultDecodedBufferSize);\n'
         '  DecodedBuffer = PoolObject.ReownOrClaimBuffer(sizeof(*DecodedBuffer) * DecodedCapacity);'),
        ('    while (1) {\n      InstructionSize = 0;',
         '    while (1) {\n'
         '      // Keep the bound effective with assertions disabled, including\n'
         '      // failed/overlapping instructions and paused multiblock decoding.\n'
         '      if (DecodedSize >= DecodedCapacity) {\n'
         '        FinalInstruction = true;\n'
         '        break;\n'
         '      }\n'
         '      InstructionSize = 0;')])
    edit('Source/Windows/WOW64/Module.cpp', [
        ('[FEX3-SCRATCH] v1 reuse disowned compiler buffers before growth; capacities unchanged',
         '[FEX3-SCRATCH] v2 kit16 decoder capacity follows block limit; IR capacity and JIT limits unchanged')])
    return changed
