"""Pinned FEX adaptations for Horizon's separate RW and RX JIT mappings.

The separate FEX2 runtime installs the host ABI and the exception bridge.
"""
from pathlib import Path
import hashlib
import json
import subprocess

PIN = 'e2f973fe931e6dc2ce523795e51ca1ac3ca85816'
SUBMODULE_PINS = {'External/rpmalloc': '09142d726429416bfa7b459151515fe3ab7622dd'}


def apply(source, project, output):
    source, project = Path(source), Path(project)
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise RuntimeError(f'FEX revision mismatch: {head}')
    for prefix, pin in SUBMODULE_PINS.items():
        recorded = subprocess.check_output(['git', '-C', str(source), 'rev-parse', f'HEAD:{prefix}'], text=True).strip()
        actual = subprocess.check_output(['git', '-C', str(source / prefix), 'rev-parse', 'HEAD'], text=True).strip()
        if recorded != pin or actual != pin:
            raise RuntimeError(f'{prefix}: expected pinned submodule {pin}, got {recorded}/{actual}')
    originals, patched = {}, {}

    def original(name):
        if name not in originals:
            prefix = next((p for p in SUBMODULE_PINS if name.startswith(p + '/')), '')
            relative = name[len(prefix)+1:] if prefix else name
            originals[name] = subprocess.check_output(['git', '-C', str(source / prefix), 'show', f'HEAD:{relative}']).decode()
            patched[name] = originals[name]
        return patched[name]

    def replace(name, old, new, count=1):
        data = original(name)
        if data.count(old) != count:
            raise RuntimeError(f'{name}: expected {count} anchors for {old[:100]!r}, got {data.count(old)}')
        patched[name] = data.replace(old, new)

    def include(name):
        replace(name, '// SPDX-License-Identifier: MIT\n',
                '// SPDX-License-Identifier: MIT\n#include "horizon_host.h"\n')

    # Keep every adaptation isolated to a separate source/build tree.
    name = 'Source/Windows/WOW64/CMakeLists.txt'
    replace(name, '  Module.cpp\n', '  Module.cpp\n  "${PES13_HORIZON_DIR}/module_host.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_host_call.S"\n'
            '  "${PES13_HORIZON_DIR}/module_memory.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_counter.cpp"\n')
    name = 'CMakeLists.txt'
    # Insert before the first target definition, but after language selection.
    replace(name, 'project(FEX C CXX ASM)',
            'project(FEX C CXX ASM)\n\n'
            'if(NOT PES13_HORIZON_DIR)\n  message(FATAL_ERROR "PES13_HORIZON_DIR is required for this patched checkout")\nendif()\n'
            'include_directories("${PES13_HORIZON_DIR}")\n'
            'add_compile_definitions(PES13_FEX_HORIZON=1)')
    name = 'Source/Windows/WOW64/libwow64fex.def'
    replace(name, 'EXPORTS\n', 'EXPORTS\n  PES13FexSetHost\n  PES13FexHostReady\n  PES13FexHandleException\n')

    name = 'Source/Windows/WOW64/Module.cpp'
    include(name)
    replace(name, 'void BTCpuProcessInit() {\n',
            'void BTCpuProcessInit() {\n'
            '  // Never fall back to a Windows RWX allocation on Horizon.\n'
            '  if (!PES13FexHostReady()) __builtin_trap();\n'
            '  PES13FexHostPreflight();\n')
    for anchor, message in (
        ('  FEX::Windows::InitCRTProcess();', 'process CRT'),
        ('  FEX::Windows::SetupThreadHandlers();', 'thread handlers'),
        ('  CTX->InitCore();', 'core init'),
        ('  CPUFeatures.emplace(*CTX);', 'images mapped'),
        ('  auto* Thread = CTX->CreateThread();', 'thread create'),
        ('  Threads.emplace(ThreadTID, Thread);', 'thread ready'),
    ):
        replace(name, anchor, '  PES13FexLog("[FEX2] ' + message + '");\n' + anchor)
    replace(name, '  FEX::Windows::InitCRTProcess();',
            '  PES13FexAllocationPreflight();\n'
            '  PES13FexCounterPreflight();\n'
            '  FEX::Windows::InitCRTProcess();\n'
            '  PES13FexLog("[FEX2] process CRT ready");\n'
            '  PES13FexHeapPreflight();')
    replace(name, '  Context::LockJITContext();\n  CTX->ExecuteThread',
            '  static std::atomic<bool> Entered {false};\n'
            '  if (!Entered.exchange(true, std::memory_order_relaxed)) PES13FexLog("[FEX2] first x86 dispatch");\n'
            '  Context::LockJITContext();\n  CTX->ExecuteThread')
    # Initialization can fault while reserving/committing the lookup tables,
    # before a thread is published in TLS. Upstream CallRetStack dereferences it.
    replace(name, 'if (FEX::Windows::CallRetStack::HandleAccessViolation(Thread, FaultAddress, Context->X25))',
            'if (Thread && FEX::Windows::CallRetStack::HandleAccessViolation(Thread, FaultAddress, Context->X25))')
    replace(name, 'if (FEX::Windows::JITGuardPage::HandleJITGuardPage(Thread,',
            'if (Thread && FEX::Windows::JITGuardPage::HandleJITGuardPage(Thread,')
    replace(name, 'NTSTATUS BTCpuResetToConsistentState(EXCEPTION_POINTERS* Ptrs) {',
            'extern "C" int PES13FexHandleException(EXCEPTION_POINTERS* Ptrs) {\n'
            '  if (!Ptrs || !Ptrs->ContextRecord || !Ptrs->ExceptionRecord || !CTX) return 0;\n'
            '  return BTCpuResetToConsistentStateImpl(Ptrs) ? 1 : 0;\n'
            '}\n\nNTSTATUS BTCpuResetToConsistentState(EXCEPTION_POINTERS* Ptrs) {')
    # Do not silently report a handled lazy-commit fault if Wine ran out of VA.
    name = 'Source/Windows/Common/OvercommitTracker.h'
    replace(name, '        NtQueryVirtualMemory(NtCurrentProcess(), reinterpret_cast<void*>(FaultAddress), MemoryBasicInformation, &Info, sizeof(Info), nullptr);',
            '        if (NtQueryVirtualMemory(NtCurrentProcess(), reinterpret_cast<void*>(FaultAddress), MemoryBasicInformation, &Info, sizeof(Info), nullptr)) return false;')
    replace(name, '        VirtualAlloc(reinterpret_cast<void*>(Info.AllocationBase), CommitSize, MEM_COMMIT, PAGE_READWRITE);',
            '        return VirtualAlloc(reinterpret_cast<void*>(Info.AllocationBase), CommitSize, MEM_COMMIT, PAGE_READWRITE) != nullptr;')

    # Native and guest share the forwarder's 32-bit address space. Do not add
    # an artificial address requirement: UINT32_MAX exceeds Wine's WOW limit
    # (0xffff0000), so NtAllocateVirtualMemoryEx rejects even a 4 KB heap.
    # Let Wine enforce its limits and preserve caller-supplied Ex parameters.
    name = 'Source/Windows/Common/WinAPI/Alloc.cpp'
    include(name)
    replace(name, '#ifndef _M_ARM64EC',
            '#if !defined(_M_ARM64EC) && !defined(PES13_FEX_HORIZON)', count=5)
    for function, args in (
        ('VirtualAlloc', 'lpAddress, dwSize, flAllocationType, flProtect'),
        ('VirtualAlloc2', 'BaseAddress, Size, AllocationType, PageProtection'),
    ):
        start = original(name).index(f'DLLEXPORT_FUNC(void*, {function},')
        pos = patched[name].index('  if (Status) {\n', start)
        address, size, allocation, protect = args.split(', ')
        diagnostic = ('    PES13FexLogAllocationFailure("' + function + '", '
                      'reinterpret_cast<uintptr_t>(' + address + '), ' + size + ', '
                      + allocation + ', ' + protect + ', static_cast<uint32_t>(Status));\n')
        patched[name] = patched[name][:pos] + patched[name][pos:].replace(
            '  if (Status) {\n', '  if (Status) {\n' + diagnostic, 1)

    # rpmalloc's desktop geometry reserves 256 MiB plus the same amount for
    # alignment for its first tiny block. Native and guest mappings share the
    # Switch forwarder's low 4 GiB, whose holes cannot satisfy that request.
    # Keep the allocator and size classes, but use power-of-two 32 MiB spans
    # and large pages. At least two maximum-sized blocks must fit: the pinned
    # page-full/free path does not support a size class with just one block.
    # Change the pinned submodule only in the isolated Horizon source tree.
    name = 'External/rpmalloc/rpmalloc/rpmalloc.c'
    replace(name, '#include "rpmalloc.h"', '#include "rpmalloc.h"\n#include "horizon_host.h"')
    replace(name, '#define LARGE_PAGE_SIZE_SHIFT 26', '#define LARGE_PAGE_SIZE_SHIFT 25')
    replace(name, '#define SPAN_SIZE (256 * 1024 * 1024)', '#define SPAN_SIZE (32 * 1024 * 1024)')
    replace(name, '#define SPAN_MASK (~((uintptr_t)(SPAN_SIZE - 1)))',
            '#define SPAN_MASK (~((uintptr_t)(SPAN_SIZE - 1)))\n'
            '_Static_assert((SPAN_SIZE & (SPAN_SIZE - 1)) == 0, "span must be a power of two");\n'
            '_Static_assert(SPAN_SIZE >= LARGE_PAGE_SIZE && !(SPAN_SIZE % LARGE_PAGE_SIZE), "span/page geometry");\n'
            '_Static_assert(LARGE_PAGE_SIZE >= 2 * LARGE_BLOCK_SIZE_LIMIT + PAGE_HEADER_SIZE, "multiple blocks per page required");')
    replace(name, '\tif (!ptr) {\n\t\tif (global_memory_interface->map_fail_callback)',
            '\tif (!ptr) {\n\t\tPES13FexHeapFailure("reserve", map_size);\n'
            '\t\tif (global_memory_interface->map_fail_callback)')
    replace(name, '\t\trpmalloc_assert(0, "Failed to commit virtual memory block");',
            '\t\tPES13FexHeapFailure("commit", size);')

    # A conservative Cortex-A57 bring-up profile. Do not read privileged CPU
    # ID registers or depend on the Windows ARM64 hardware registry existing.
    name = 'Source/Windows/Common/CPUFeatures.cpp'
    replace(name, '  HKEY Key = OpenProcessorKey(0);',
            '  // First bring-up: ARMv8.0 + NEON, no optional LSE/RCPC/SVE features.\n'
            '  // Optional feature enablement needs a separate on-device probe.\n'
            '  FEXCore::HostFeatures Baseline {};\n'
            '  Baseline.DCacheLineLog2 = 4;\n'
            '  Baseline.Supports3DNow = true;\n'
            '  Baseline.HostType = HostType;\n'
            '  Baseline.ProcessPID = ProcessPID;\n'
            '  Baseline.CPUMIDRs.assign(4, 0x411fd071);\n'
            '  return Baseline;\n\n  HKEY Key = OpenProcessorKey(0);')

    name = 'FEXCore/include/FEXCore/Utils/AllocatorHooks.h'
    include(name)
    replace(name, '  DWORD Flags = (Commit ? MEM_COMMIT : 0) | MEM_RESERVE | MEM_TOP_DOWN;',
            '  if (Execute) {\n'
            '    if (Base || !Commit) return nullptr; // Unsupported fixed/lazy native JIT allocation.\n'
            '    return PES13FexAllocateCode(Size);\n'
            '  }\n'
            '  DWORD Flags = (Commit ? MEM_COMMIT : 0) | MEM_RESERVE | MEM_TOP_DOWN;')
    replace(name, '  ::VirtualFree(Ptr, 0, MEM_RELEASE);',
            '  if (PES13FexReleaseCode(Ptr)) return;\n  ::VirtualFree(Ptr, 0, MEM_RELEASE);')

    name = 'CodeEmitter/CodeEmitter/Buffer.h'
    include(name)
    replace(name, '  template<typename T>\n  requires',
            '  static void* Writable(void* Address, size_t Length) {\n'
            '    return PES13FexWriteAlias(Address, Length);\n'
            '  }\n\n  template<typename T>\n  requires')
    replace(name, 'std::memcpy(CurrentOffset, &Data, sizeof(Data));',
            'std::memcpy(Writable(CurrentOffset, sizeof(Data)), &Data, sizeof(Data));')
    replace(name, 'memcpy(CurrentOffset, String, StringLength);',
            'memcpy(Writable(CurrentOffset, StringLength), String, StringLength);')
    replace(name, 'std::memset(CurrentOffset, 0, Size - CurrentAlignment);',
            'std::memset(Writable(CurrentOffset, Size - CurrentAlignment), 0, Size - CurrentAlignment);')
    replace(name, '__builtin___clear_cache(static_cast<char*>(Begin), static_cast<char*>(Begin) + Length);',
            'PES13FexFlushCode(Begin, Length);')

    name = 'CodeEmitter/CodeEmitter/Emitter.h'
    replace(name, '  CNTFRQ_EL0 = GenSystemReg<0b11, 0b011, 0b1110, 0b0000, 0b000>,',
            '  CNTFRQ_EL0 = GenSystemReg<0b11, 0b011, 0b1110, 0b0000, 0b000>,\n'
            '  CNTPCT_EL0 = GenSystemReg<0b11, 0b011, 0b1110, 0b0000, 0b001>,')
    replace(name, '*Instruction = Inst;', '*PES13FexWritable(Instruction) = Inst;', count=5)

    # A shared physical counter for initializers, profiling and timed locks.
    # Clang's __builtin_readcyclecounter() emits CNTVCT_EL0 on Windows ARM64,
    # which traps on Horizon even though the Cortex-A57 implements the register.
    for name in ('FEXCore/include/FEXCore/Utils/SpinWaitLock.h',
                 'FEXCore/include/FEXCore/Utils/SHMStats.h'):
        replace(name, '#pragma once', '#pragma once\n#include "horizon_counter.h"')
        data = original(name)
        begin = data.index('static inline uint64_t GetCycleCounter() {')
        end = data.index('\n}', begin) + 2
        patched[name] = data[:begin] + ('static inline uint64_t GetCycleCounter() {\n'
                                        '  return pes13_fex_counter();\n}') + data[end:]

    # RDTSC/RDTSCP and the Windows performance-counter pseudo-op lower through
    # this IR operation. Preserve its requested ordering, without requiring ECV.
    name = 'FEXCore/Source/Interface/Core/JIT/ALUOps.cpp'
    data = original(name)
    begin = data.index('DEF_OP(CycleCounter) {')
    end = data.index('\nDEF_OP(AddShift)', begin)
    patched[name] = data[:begin] + ('DEF_OP(CycleCounter) {\n'
        '  auto Op = IROp->C<IR::IROp_CycleCounter>();\n'
        '  if (Op->SelfSynchronizingLoads) isb();\n'
        '  mrs(GetReg(Node), ARMEmitter::SystemRegister::CNTPCT_EL0);\n'
        '}\n') + data[end:]

    name = 'FEXCore/Source/Interface/Core/JIT/JIT.cpp'
    include(name)
    replace(name, '#include "horizon_host.h"', '#include "horizon_host.h"\n#include "horizon_counter.h"')
    replace(name, 'static_cast<uint64_t>(__builtin_readcyclecounter())', 'pes13_fex_counter()')
    replace(name, 'std::atomic_ref<uint32_t>(*reinterpret_cast<uint32_t*>(CallerAddress))',
            'std::atomic_ref<uint32_t>(*PES13FexWritable(reinterpret_cast<uint32_t*>(CallerAddress)))', count=2)
    replace(name, 'std::atomic_ref<uint32_t>(*reinterpret_cast<uint32_t*>(JumpThunkStartAddress))',
            'std::atomic_ref<uint32_t>(*PES13FexWritable(reinterpret_cast<uint32_t*>(JumpThunkStartAddress)))', count=2)
    replace(name, 'std::atomic_ref<uint64_t>(Record->HostCode).store',
            'std::atomic_ref<uint64_t>(*PES13FexWritable(&Record->HostCode)).store')
    replace(name, 'asm volatile("dc cvau, %0; dsb ish" : : "r"(Record->HostCode) :);',
            'PES13FexFlushCode(&Record->HostCode, sizeof(Record->HostCode));')
    replace(name, 'memcpy(AllocatedInfo.BufferAllocationOffset, TempCodeBuffer, CodeData.Size);',
            'memcpy(PES13FexWriteAlias(AllocatedInfo.BufferAllocationOffset, CodeData.Size), TempCodeBuffer, CodeData.Size);')
    replace(name, 'memcpy(Dest, HostBytes.data(), HostBytes.size());',
            'memcpy(PES13FexWriteAlias(Dest, HostBytes.size()), HostBytes.data(), HostBytes.size());')

    name = 'FEXCore/Source/Utils/ArchHelpers/Arm64.cpp'
    include(name)
    replace(name, '__builtin___clear_cache(static_cast<char*>(Begin), static_cast<char*>(Begin) + Length);',
            'PES13FexFlushCode(Begin, Length);')
    replace(name, 'UniqueSpinMutex lk(&InlineTail->SpinLockFutex);',
            'UniqueSpinMutex lk(PES13FexWritable(&InlineTail->SpinLockFutex));')
    # Preserve RX program counters and branch offsets; only the store uses RW.
    for index, count in ((0, 4), (1, 2), (-1, 2)):
        replace(name, f'std::atomic_ref<uint32_t>(PC[{index}]).store',
                f'std::atomic_ref<uint32_t>(*PES13FexWritable(&PC[{index}])).store', count=count)

    name = 'FEXCore/Source/Interface/Core/SharedCodeBufferManager.cpp'
    start = original(name).index('  // Protect the last page of the allocated buffer')
    end = original(name).index('\n  if (ShouldBeNamed)', start)
    patched[name] = patched[name][:start] + (
        '  // Horizon CodeMemory permissions cannot be changed by Wine VirtualProtect.\n'
        '  // Allocate() still excludes the final page through UsableSize(). The\n'
        '  // temporary compilation buffer retains its separate real guard page.\n'
        '  // The host alias adapter also rejects writes across an allocation.\n') + patched[name][end:]

    # Validate the whole set before writing: preserve any unexpected local work.
    dirty = set(subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only', 'HEAD'], text=True).splitlines())
    for prefix in SUBMODULE_PINS:
        dirty.discard(prefix)
        dirty.update(prefix + '/' + name for name in subprocess.check_output(
            ['git', '-C', str(source / prefix), 'diff', '--name-only', 'HEAD'], text=True).splitlines())
    if set(dirty) - set(patched):
        raise RuntimeError(f'Unexpected modified source outside the Horizon patch set: {set(dirty) - set(patched)}')
    # Accept an earlier version only when its bytes match our saved, pinned
    # patch manifest. This permits upgrades without resetting an entire tree.
    previous = {}
    for manifest in (Path(output), project / 'local/fex1/horizon-module/patches.json'):
        if manifest.exists():
            old_report = json.loads(manifest.read_text())
            if old_report.get('fex_commit') == PIN:
                for item in old_report['files']:
                    previous.setdefault(item['path'], set()).add(item['patched_sha256'])
    for name, data in patched.items():
        current = (source / name).read_text()
        if current not in (originals[name], data) and hashlib.sha256(current.encode()).hexdigest() not in previous.get(name, set()):
            raise RuntimeError(f'Refusing to overwrite local changes: {source / name}')
    report = {'fex_commit': PIN, 'submodule_commits': SUBMODULE_PINS, 'files': [], 'hardware_tested': False,
              'exports_host_exception_bridge': True,
              'native_integration_builder': 'tools/build-fex-runtime.py'}
    for name, data in patched.items():
        if (source / name).read_text() != data:
            (source / name).write_text(data)
        report['files'].append({'path': name, 'upstream_sha256': hashlib.sha256(originals[name].encode()).hexdigest(),
                                'patched_sha256': hashlib.sha256(data.encode()).hexdigest()})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report
