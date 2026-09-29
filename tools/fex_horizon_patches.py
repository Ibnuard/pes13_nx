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
            '  "${PES13_HORIZON_DIR}/module_heap.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_profile.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_exception.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_smc.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_counter.cpp"\n')
    replace(name, '  Module.cpp\n', '  Module.cpp\n  "${PES13_HORIZON_DIR}/module_fpu.cpp"\n'
            '  "${PES13_HORIZON_DIR}/module_jit_timing.cpp"\n')
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
    replace(name, '#include "horizon_host.h"', '#include "horizon_host.h"\n#include "horizon_fpu.h"\n#include "horizon_jit_timing.h"')
    replace(name, 'namespace Context {', 'namespace Context {\nstatic bool HorizonReducedPrecision;')
    replace(name, '  memcpy(State.mm, XSave->FloatRegisters, sizeof(State.mm));',
            '  PES13FexImportX87(State.mm, XSave->FloatRegisters, XSave->StatusWord,\n'
            '                    XSave->ControlWord, HorizonReducedPrecision);\n'
            '  State.mxcsr = XSave->MxCsr & 0xffff;')
    replace(name, '  memcpy(XSave->FloatRegisters, State.mm, sizeof(State.mm));',
            '  const uint16_t HorizonStatus = State.flags[FEXCore::X86State::X87FLAG_TOP_LOC] << 11;\n'
            '  PES13FexExportX87(XSave->FloatRegisters, State.mm, HorizonStatus, HorizonReducedPrecision);\n'
            '  XSave->MxCsr = State.mxcsr;\n'
            '  XSave->MxCsr_Mask = 0xffc0;\n'
            '  for (unsigned i = 0; i < 8; ++i)\n'
            '    memcpy(Context->FloatSave.RegisterArea + i * 10, &XSave->FloatRegisters[i], 10);')
    replace(name, 'FEXCore::FPState::ConvertFromAbridgedFTW(XSave->StatusWord, State.mm, XSave->TagWord)',
            'FEXCore::FPState::ConvertFromAbridgedFTW(XSave->StatusWord,\n'
            '    *reinterpret_cast<uint64_t (*)[8][2]>(XSave->FloatRegisters), XSave->TagWord)')
    replace(name, '  XSave->MxCsr = 0x1f80;\n', '')
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
    replace(name, '  FEXCore::Config::ReloadMetaLayer();',
            '  FEXCore::Config::ReloadMetaLayer();\n'
            '  PES13FexApplyPerformanceProfile();\n'
            '  PES13FexJitTimingInit();\n'
            '  FEX_CONFIG_OPT(HorizonReduced, X87REDUCEDPRECISION);\n'
            '  Context::HorizonReducedPrecision = HorizonReduced();\n'
            '  PES13FexLog("[FEX3-FP] context v1 MXCSR, x87 TOP/F64, legacy registers");\n'
            '  PES13FexLog("[FEX3-ALIAS] generation-validated PE alias snapshots");')
    replace(name, '  NtAllocateVirtualMemory(NtCurrentProcess(), &Addr, (1U << 31) - 1, &Size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);',
            '  const NTSTATUS TrampolineStatus = NtAllocateVirtualMemory(NtCurrentProcess(), &Addr,\n'
            '    (1U << 31) - 1, &Size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);\n'
            '  if (TrampolineStatus || !Addr) {\n'
            '    PES13FexLogAllocationFailure("syscall trampoline", 0, Size, MEM_RESERVE | MEM_COMMIT,\n'
            '                                  PAGE_EXECUTE_READWRITE, TrampolineStatus);\n'
            '    PES13FexHeapFailure("syscall trampoline", Size);\n'
            '  }')
    replace(name, '  CTX->InitCore();',
            '  PES13FexLog("[FEX3-SMC] v2 static game/D3D9 text entry guards; dynamic code keeps instruction guards");\n'
            '  PES13FexLog("[FEX3-MEM] v3 resident native L1; enabled L2 lazy commit<=64 KiB");\n'
            '  PES13FexLog("[FEX3-SCRATCH] v1 reuse disowned compiler buffers before growth; capacities unchanged");\n'
            '  PES13FexLog("[FEX3-CODE] v1 negotiate fresh cache size; preserve live code references");\n'
            '  PES13FexLog("[FEX3-CALLRET] v1 prediction stack=256 KiB/thread; guard recovery retained");\n'
            '  PES13FexLog("[FEX3-GEX] v1 bounded exception-route diagnostics; behavior unchanged");\n'
            '  CTX->InitCore();')
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
    replace(name, 'if (OvercommitTracker && OvercommitTracker->HandleAccessViolation(FaultAddress))',
            'if (Exception->ExceptionInformation[0] != 8 && OvercommitTracker && OvercommitTracker->HandleAccessViolation(FaultAddress))')
    replace(name, '  auto* Exception = Ptrs->ExceptionRecord;',
            '  auto* Exception = Ptrs->ExceptionRecord;\n  uint32_t HorizonTrace = 0;')
    replace(name, '    if (Thread) {\n      std::scoped_lock Lock(ThreadCreationMutex);',
            '    if (Thread) {\n'
            '      HorizonTrace = PES13FexBeginGuestFaultTrace(GetCurrentThreadId(),\n'
            '                                                Context->Pc, FaultAddress);\n'
            '      std::scoped_lock Lock(ThreadCreationMutex);\n'
            '      PES13FexTraceGuestFault(HorizonTrace, "smc-lock", Context->Pc, FaultAddress);')
    replace(name, '      if (InvalidationTracker->HandleRWXAccessViolation(Thread, Context->Pc, FaultAddress)) {',
            '      if (InvalidationTracker->HandleRWXAccessViolation(Thread, Context->Pc, FaultAddress)) {\n'
            '        PES13FexTraceGuestFault(HorizonTrace, "smc-handled", Context->Pc, FaultAddress);')
    replace(name, '  if (!Thread || !IsAddressInJit(Context->Pc)) {\n    return false;',
            '  PES13FexTraceGuestFault(HorizonTrace, "classify", Context->Pc, Exception->ExceptionCode);\n'
            '  if (!Thread || !IsAddressInJit(Context->Pc)) {\n'
            '    PES13FexTraceGuestFault(HorizonTrace, "native-fault", Context->Pc, Exception->ExceptionCode);\n'
            '    return false;')
    replace(name, '  WOW64_CONTEXT* WowContext = Context::ReconstructWowContext(Context);',
            '  PES13FexTraceGuestFault(HorizonTrace, "reconstruct", Context->Pc, 0);\n'
            '  WOW64_CONTEXT* WowContext = Context::ReconstructWowContext(Context);\n'
            '  PES13FexTraceGuestFault(HorizonTrace, "guest-context", WowContext->Eip, WowContext->Esp);')
    replace(name, '  Context::UnlockJITContext();\n  NtRaiseException(&GuestException, GetTLS().EntryContext(), FirstChance);',
            '  PES13FexTraceGuestFault(HorizonTrace, "unlock", WowContext->Eip, GuestException.ExceptionCode);\n'
            '  Context::UnlockJITContext();\n'
            '  PES13FexTraceGuestFault(HorizonTrace, "raise", GetTLS().EntryContext()->Pc, FirstChance);\n'
            '  const auto HorizonStatus = NtRaiseException(&GuestException, GetTLS().EntryContext(), FirstChance);\n'
            '  PES13FexTraceGuestFault(HorizonTrace, "raise-return", WowContext->Eip, static_cast<uint32_t>(HorizonStatus));')
    replace(name, 'NTSTATUS BTCpuResetToConsistentState(EXCEPTION_POINTERS* Ptrs) {',
            'extern "C" int PES13FexHandleException(EXCEPTION_POINTERS* Ptrs) {\n'
            '  if (!Ptrs || !Ptrs->ContextRecord || !Ptrs->ExceptionRecord || !CTX) return 0;\n'
            '  return BTCpuResetToConsistentStateImpl(Ptrs) ? 1 : 0;\n'
            '}\n\nNTSTATUS BTCpuResetToConsistentState(EXCEPTION_POINTERS* Ptrs) {')

    # Horizon section aliases can remain physically writable even when Wine
    # reports RX. Keep MTRACK and its normal invalidations, but use FEX's own
    # per-instruction SMC guards for blocks touching tracked writable code.
    # Read-only Wine/game text does not acquire these runtime checks.
    name = 'FEXCore/Source/Interface/Core/Core.cpp'
    include(name)
    replace(name, '#include "horizon_host.h"',
            '#include "horizon_host.h"\n#include "horizon_smc.h"\n#include "horizon_stall.h"\n')
    anchor = 'uint64_t ContextImpl::RestoreRIPFromHostPC(FEXCore::Core::InternalThreadState* Thread, uint64_t HostPC) {'
    replace(name, anchor, anchor + '\n'
            '  static_assert(offsetof(FEXCore::Core::CpuStateFrame, State) == 0);\n'
            '  static_assert(offsetof(FEXCore::Core::CPUState, InlineJITBlockHeader) == PES13_FEX_FRAME_BLOCK_OFFSET);\n'
            '  static_assert(offsetof(FEXCore::Core::CPUState, rip) == PES13_FEX_FRAME_RIP_OFFSET);\n'
            '  static_assert(sizeof(CPU::CPUBackend::JITCodeTail) == sizeof(pes13_fex_observed_tail));\n'
            '  static_assert(offsetof(CPU::CPUBackend::JITCodeTail, Size) == offsetof(pes13_fex_observed_tail, size));\n'
            '  static_assert(offsetof(CPU::CPUBackend::JITCodeTail, RIP) == offsetof(pes13_fex_observed_tail, rip));\n')
    replace(name, '      const auto& Block = CodeBlocks[j];',
            '      const auto& Block = CodeBlocks[j];\n'
            '      const bool HorizonSMC = PES13FexNeedsCodeValidation(Block.Entry, Block.Size,\n'
            '        [&](uint64_t Address) { return SyscallHandler->QueryGuestExecutableRange(Thread, Address); });\n'
            '      bool HorizonEntrySMC = false;\n'
            '      if (HorizonSMC && Config.SMCChecks != FEXCore::Config::CONFIG_SMC_FULL &&\n'
            '          !Block.ForceFullSMCDetection && !WantsDiskCachePatching &&\n'
            '          Block.BlockStatus == Frontend::Decoder::DecodedBlockStatus::SUCCESS &&\n'
            '          PES13FexPerformanceProfile()) {\n'
            '        if (const auto Image = SyscallHandler->LookupExecutableFileSection(Thread, Block.Entry))\n'
            '          HorizonEntrySMC = Image->EndVA > Image->FileStartVA &&\n'
            '            PES13FexCanBatchSMC(Image->FileStartVA, Image->EndVA - Image->FileStartVA,\n'
            '              Image->FileInfo.Filename.c_str(), Block.Entry, Block.Size);\n'
            '      }\n'
            '      PES13FexRecordSMC(Block.NumInstructions, HorizonEntrySMC ? 2 :\n'
            '        (HorizonSMC || Block.ForceFullSMCDetection || Config.SMCChecks == FEXCore::Config::CONFIG_SMC_FULL) ? 1 : 0);')
    replace(name, 'if (Config.SMCChecks == FEXCore::Config::CONFIG_SMC_FULL || Block.ForceFullSMCDetection)',
            'if (Config.SMCChecks == FEXCore::Config::CONFIG_SMC_FULL || Block.ForceFullSMCDetection ||\n'
            '            (HorizonSMC && (!HorizonEntrySMC || i == 0)))')
    replace(name, '          auto CodeChanged = Thread->OpDispatcher->_ValidateCode(CRC, InstAddressReg, DecodedInfo->InstSize);',
            '''          IR::OrderedNode *CodeChanged = Thread->OpDispatcher->_ValidateCode(CRC, InstAddressReg, DecodedInfo->InstSize);
          if (HorizonEntrySMC) {
            // Include every remaining byte; one failure edge per basic block.
            // CodeLength is uint8_t. Chunk without page over-read or truncation.
            for (uint64_t Offset = DecodedInfo->InstSize; Offset < Block.Size;) {
              const auto Length = static_cast<uint8_t>(std::min<uint64_t>(255, Block.Size - Offset));
              auto Bytes = reinterpret_cast<uint8_t*>(Block.Entry + Offset);
              auto Expected = Thread->OpDispatcher->Constant(FEXCore::Utils::crc32(Bytes, Length));
              auto Address = Thread->OpDispatcher->_EntrypointOffset(GPRSize, Block.Entry + Offset - GuestRIP);
              auto Changed = Thread->OpDispatcher->_ValidateCode(Expected, Address, Length);
              CodeChanged = Thread->OpDispatcher->_Or(GPRSize, CodeChanged, Changed);
              Offset += Length;
            }
          }''')

    name = 'Source/Windows/Common/InvalidationTracker.cpp'
    include(name)
    # Notifications describe the application's protection, not the temporary
    # native MTRACK trap. Do not keep a restored RX range permanently RWX after
    # loader relocation/unpacking; otherwise every instruction gains SMC code.
    replace(name, '        RWXIntervals.Insert(ProtInterval);\n      }',
            '        RWXIntervals.Insert(ProtInterval);\n'
            '      } else {\n'
            '        RWXIntervals.Remove(ProtInterval);\n'
            '      }')
    replace(name, '      NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, UntrapProt, &TmpProt);',
            '      const auto Status = NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, UntrapProt, &TmpProt);\n'
            '      if (Status) {\n'
            '        PES13FexLogSMCProtectFailure(FaultAddress, TmpSize, UntrapProt, Status);\n'
            '        return false; // Do not resume an unchanged, still-faulting store.\n'
            '      }')
    replace(name, '      NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, ForWriteLocked ? GetUntrapProt(Address) : GetTrapProt(Address), &TmpProt);',
            '      const auto Prot = ForWriteLocked ? GetUntrapProt(Address) : GetTrapProt(Address);\n'
            '      const auto Status = NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, Prot, &TmpProt);\n'
            '      if (Status) PES13FexLogSMCProtectFailure(Address, TmpSize, Prot, Status);')
    # PES exhausts VA even with 8 MiB heap spans. Every old lookup reserves
    # 25 MiB, although this pinned FEX defaults DisableL2Cache=true. Reserve
    # only L1 in that mode, with exactly the same lookup behavior as before.
    # If L2 is explicitly enabled, keep the full guest index, 16 MiB backing
    # and existing eviction/L3 fallback. Do not shrink guest address masks.
    name = 'FEXCore/Source/Interface/Core/Core.cpp'
    replace(name, '#include "horizon_host.h"', '#include "horizon_host.h"\n#include "horizon_jit_timing.h"')
    replace(name, 'ContextImpl::CompileCodeResult ContextImpl::CompileCode(FEXCore::Core::InternalThreadState* Thread, uint64_t GuestRIP, uint64_t MaxInst) {',
            'ContextImpl::CompileCodeResult ContextImpl::CompileCode(FEXCore::Core::InternalThreadState* Thread, uint64_t GuestRIP, uint64_t MaxInst) {\n'
            '  PES13FexJitScope HorizonCompileTiming{1};')
    replace(name, 'uintptr_t ContextImpl::CompileBlock(FEXCore::Core::CpuStateFrame* Frame, uint64_t GuestRIP, uint64_t MaxInst) {',
            'uintptr_t ContextImpl::CompileBlock(FEXCore::Core::CpuStateFrame* Frame, uint64_t GuestRIP, uint64_t MaxInst) {\n'
            '  PES13FexJitReportScope HorizonReport;\n'
            '  PES13FexJitScope HorizonDispatchTiming{0};')
    # Cache-OFF was still locking/searching ImageTracker for every cold compile.
    # Region is consumed only by disk cache and CodeMapWriter below; debug/JIT
    # naming and SMC validation use their own lookups and remain unchanged.
    replace(name, '  std::optional<ExecutableFileSectionInfo> Region = SyscallHandler->LookupExecutableFileSection(Thread, GuestRIP);',
            '  const std::optional<ExecutableFileSectionInfo> Region =\n'
            '    (DiskCache.IsReadingDiskCache() || DiskCache.IsWritingDiskCache() || CodeMapWriter)\n'
            '      ? SyscallHandler->LookupExecutableFileSection(Thread, GuestRIP) : std::nullopt;')
    replace(name, '    Hit = DiskCache.Lookup(Thread, Region, GuestRIP, DiskCacheGuestCodeKey);',
            '    if (DiskCache.IsReadingDiskCache()) {\n'
            '      Hit = DiskCache.Lookup(Thread, Region, GuestRIP, DiskCacheGuestCodeKey);\n'
            '    }')
    name = 'Source/Windows/Common/InvalidationTracker.cpp'
    replace(name, '#include "horizon_host.h"', '#include "horizon_host.h"\n#include "horizon_jit_timing.h"')
    replace(name, 'void InvalidationTracker::InvalidateIntervalInternalLocked(uint64_t Address, uint64_t Size) {',
            'void InvalidationTracker::InvalidateIntervalInternalLocked(uint64_t Address, uint64_t Size) {\n'
            '  PES13FexJitScope HorizonInvalidateTiming{2};')

    name = 'FEXCore/Source/Interface/Core/LookupCache.h'
    # Mix the page/module bits into the resident L1 index. The old low-RIP
    # index aliases blocks 64 KiB apart. Retain full guest tags, allocation,
    # locks, invalidation and L2/L3 fallback; all producers and probes agree.
    replace(name, '[Address & L1PointerMask]', '[(Address ^ (Address >> 16)) & L1PointerMask]', count=2)
    replace(name, '[GuestAddress & L1PointerMask]', '[(GuestAddress ^ (GuestAddress >> 16)) & L1PointerMask]')
    # Disabled L2 uses a fully resident, zeroed 1 MiB native allocation.
    # Dynamic sizing cannot return any of it to Horizon; starting at 128 KiB
    # only adds collisions, clock calls and periodic clears on the hot path.
    replace(name, 'if (HostPtr && DynamicL1Cache()) {',
            'if (HostPtr && !DisableL2Cache() && DynamicL1Cache()) {')
    replace(name, '// Max out at 1 million entries to give each thread 16MB of L1 cache maximum.',
            '// Horizon: cap at 64K entries (1 MiB), retaining dynamic L1 growth.')
    replace(name, 'MAX_L1_ENTRIES = 1 * 1024 * 1024;', 'MAX_L1_ENTRIES = 64 * 1024;')
    replace(name, 'CODE_SIZE = 128 * 1024 * 1024;', 'CODE_SIZE = 16 * 1024 * 1024;')
    replace(name, '#include <cstdint>', '#include <cstdint>\n#include <cstring>')
    replace(name, 'private:\n  void AddL1Entry', '''private:
  // Native L1 memory is always resident. Clear entries rather than decommit
  // pages through Wine; the next dispatch must never need a VM fault here.
  void ClearLookupMemory(void* Address, size_t Size) {
    if (DisableL2Cache()) std::memset(Address, 0, Size);
    else FEXCore::Allocator::VirtualDontNeed(Address, Size, false);
  }

  void AddL1Entry''')
    replace(name, 'FEXCore::Allocator::VirtualDontNeed(reinterpret_cast<void*>(L1Pointer), CurrentL1Entries * sizeof(LookupCacheEntry), false);',
            'ClearLookupMemory(reinterpret_cast<void*>(L1Pointer), CurrentL1Entries * sizeof(LookupCacheEntry));')
    replace(name, 'FEXCore::Allocator::VirtualDontNeed(FirstZeroL1Entry, ZeroMemorySize, false);',
            'ClearLookupMemory(FirstZeroL1Entry, ZeroMemorySize);')
    name = 'FEXCore/Source/Interface/Core/LookupCache.cpp'
    replace(name, '  if (DynamicL1Cache()) {',
            '  if (!DisableL2Cache() && DynamicL1Cache()) {')
    include(name)
    replace(name, '#include "horizon_host.h"', '#include "horizon_host.h"\n#include <atomic>')
    replace(name, '  TotalCacheSize = ctx->Config.VirtualMemSize / FEXCore::Utils::FEX_PAGE_SIZE * 8 + CODE_SIZE + MAX_L1_SIZE;',
            '  const size_t IndexSize = DisableL2Cache() ? 0 : ctx->Config.VirtualMemSize / FEXCore::Utils::FEX_PAGE_SIZE * 8;\n'
            '  const size_t BackingSize = DisableL2Cache() ? 0 : CODE_SIZE;\n'
            '  TotalCacheSize = IndexSize + BackingSize + MAX_L1_SIZE;\n'
            '  static std::atomic<bool> Reported {false};\n'
            '  if (!Reported.exchange(true, std::memory_order_relaxed))\n'
            '    PES13FexLog(DisableL2Cache()\n'
            '      ? "[FEX3-LOOKUP] v3 index=rip-xor-rip16 dispatcher=L1-first L2=off native=1 MiB/thread; full resident L1"\n'
            '      : "[FEX3-LOOKUP] v3 index=rip-xor-rip16 dispatcher=L1-first L2=on full guest index; L2=16 MiB L1<=1 MiB");')
    replace(name, '                                  ctx->Config.VirtualMemSize / FEXCore::Utils::FEX_PAGE_SIZE * 8 + CODE_SIZE);',
            '                                  IndexSize + BackingSize);')
    replace(name, '  PageMemory = PagePointer + ctx->Config.VirtualMemSize / FEXCore::Utils::FEX_PAGE_SIZE * 8;',
            '  PageMemory = PagePointer + IndexSize;')
    replace(name, '  L1Pointer = PageMemory + CODE_SIZE;', '  L1Pointer = PageMemory + BackingSize;')
    replace(name, '  LOGMAN_THROW_A_FMT(PagePointer != -1ULL, "Failed to allocate PagePointer");',
            '  if (!PagePointer || PagePointer == UINTPTR_MAX)\n'
            '    PES13FexHeapFailure("lookup reserve", TotalCacheSize);')
    replace(name, '  PagePointer = reinterpret_cast<uintptr_t>(FEXCore::Allocator::VirtualAlloc(TotalCacheSize, false, false));',
            '  PagePointer = reinterpret_cast<uintptr_t>(DisableL2Cache()\n'
            '    ? PES13FexAllocateScratch(TotalCacheSize)\n'
            '    : FEXCore::Allocator::VirtualAlloc(TotalCacheSize, false, false));')
    replace(name, '  // Disable THP on the Lookup cache.',
            '  if (DisableL2Cache()) {\n'
            '    std::memset(reinterpret_cast<void*>(PagePointer), 0, TotalCacheSize);\n'
            '  } else {\n'
            '  // Disable THP on the Lookup cache.')
    replace(name, '  CTX->SyscallHandler->MarkOvercommitRange(PagePointer, TotalCacheSize);',
            '  CTX->SyscallHandler->MarkOvercommitRange(PagePointer, TotalCacheSize);\n'
            '  }')
    replace(name, '  FEXCore::Allocator::VirtualName("FEXMem_Lookup_L1", reinterpret_cast<void*>(L1Pointer), MAX_L1_SIZE);',
            '  if (!DisableL2Cache())\n'
            '    FEXCore::Allocator::VirtualName("FEXMem_Lookup_L1", reinterpret_cast<void*>(L1Pointer), MAX_L1_SIZE);')
    replace(name, '  FEXCore::Allocator::VirtualFree(reinterpret_cast<void*>(PagePointer), TotalCacheSize);\n'
            '  ctx->SyscallHandler->UnmarkOvercommitRange(PagePointer, TotalCacheSize);',
            '  if (DisableL2Cache()) {\n'
            '    PES13FexReleaseScratch(reinterpret_cast<void*>(PagePointer));\n'
            '  } else {\n'
            '    FEXCore::Allocator::VirtualFree(reinterpret_cast<void*>(PagePointer), TotalCacheSize);\n'
            '    ctx->SyscallHandler->UnmarkOvercommitRange(PagePointer, TotalCacheSize);\n'
            '  }')
    replace(name, '  FEXCore::Allocator::VirtualDontNeed(reinterpret_cast<void*>(PagePointer), TotalCacheSize, false);',
            '  ClearLookupMemory(reinterpret_cast<void*>(PagePointer), TotalCacheSize);')
    replace(name, '// We currently limit to 128MB of real memory for caching for the total cache size.',
            '// Horizon limits enabled L2 to 16 MiB; disabled L2 reserves nothing.')
    replace(name, '  FEXCore::Allocator::VirtualDontNeed(reinterpret_cast<void*>(PagePointer),\n'
            '                                      ctx->Config.VirtualMemSize / FEXCore::Utils::FEX_PAGE_SIZE * 8 + CODE_SIZE, false);',
            '  if (!DisableL2Cache())\n'
            '    FEXCore::Allocator::VirtualDontNeed(reinterpret_cast<void*>(PagePointer), L1Pointer - PagePointer, false);')
    # Clearing the entire cache invalidates the backing allocations too.
    # Reset their bump cursor so each new mapping starts with the full arena.
    replace(name, '  // TODO: Rename this member to avoid confusion with code caching',
            '  AllocateOffset = 0;\n\n'
            '  // TODO: Rename this member to avoid confusion with code caching')

    # Normal dispatcher entry (including Wine returns) didn't probe L1.
    # With L2 disabled it always spilled registers and entered CompileBlock,
    # even for an L1 hit. Keep the trap-flag check ahead of this fast path,
    # use the same tag/mask contract as BranchOps, and preserve NZCV.
    name = 'FEXCore/Source/Interface/Core/Dispatcher/Dispatcher.cpp'
    replace(name, '  ARMEmitter::ForwardLabel NoBlock;\n', '''  ARMEmitter::ForwardLabel NoBlock;

  // Horizon: the resident L1 also serves dispatcher re-entry. A miss still
  // follows the upstream L2/L3 and compilation/invalidation path.
  ARMEmitter::ForwardLabel HorizonL1Miss;
  ldp<ARMEmitter::IndexType::OFFSET>(TMP1, TMP2, STATE, offsetof(FEXCore::Core::CpuStateFrame, State.L1Pointer));
  eor(ARMEmitter::Size::i64Bit, TMP4, RipReg.R(), RipReg.R(), ARMEmitter::ShiftType::LSR, 16);
  and_(ARMEmitter::Size::i64Bit, TMP2, TMP2, TMP4, ARMEmitter::ShiftType::LSL,
       FEXCore::ilog2(sizeof(LookupCache::LookupCacheEntry)));
  add(TMP1, TMP1, TMP2);
  ldp<ARMEmitter::IndexType::OFFSET>(TMP4, TMP2, TMP1, 0);
  sub(TMP2, TMP2, RipReg);
  (void)cbnz(ARMEmitter::Size::i64Bit, TMP2, &HorizonL1Miss);
  (void)cbz(ARMEmitter::Size::i64Bit, TMP4, &HorizonL1Miss);
  br(TMP4);
  (void)Bind(&HorizonL1Miss);
''')
    name = 'FEXCore/Source/Interface/Core/JIT/BranchOps.cpp'
    replace(name,
            '    and_(ARMEmitter::Size::i64Bit, TMP2, TMP2, RipReg, ARMEmitter::ShiftType::LSL, FEXCore::ilog2(sizeof(LookupCache::LookupCacheEntry)));',
            '    eor(ARMEmitter::Size::i64Bit, TMP3, RipReg, RipReg, ARMEmitter::ShiftType::LSR, 16);\n'
            '    and_(ARMEmitter::Size::i64Bit, TMP2, TMP2, TMP3, ARMEmitter::ShiftType::LSL, FEXCore::ilog2(sizeof(LookupCache::LookupCacheEntry)));')

    # Wine's desktop path commits the complete reservation on first touch.
    # Horizon must commit only a bounded part of the tracked cache interval,
    # including after cache decommit. Return failures instead of retry loops.
    name = 'Source/Windows/Common/OvercommitTracker.h'
    include(name)
    data = original(name)
    begin = data.index('    if (Query.Enclosed) {')
    end = data.index('\n    return false;', begin)
    patched[name] = data[:begin] + (
        '    if (Query.Enclosed) {\n'
        '      return PES13FexCommitTrackedMemory(FaultAddress, Query.Interval.Offset, Query.Interval.End);\n'
        '    }\n') + data[end:]

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

    # The early-128 device run reaches the menu, then guest VA reservations
    # and Vulkan allocations fail while loading team selection. Windows FEX
    # commits a 4 MiB call/return prediction stack for every emulated thread.
    # This is a disposable prediction cache with guard-triggered recentring,
    # not the guest program's stack. Keep that recovery and both guard pages,
    # but use 256 KiB (16,384 pairs). At 34 live threads this saves 127.5 MiB
    # of both backing and guest VA. Do not publish a failed reservation.
    name = 'FEXCore/include/FEXCore/Debug/InternalThreadState.h'
    replace(name, '  static constexpr size_t CALLRET_STACK_SIZE {0x400000};',
            '  static constexpr size_t CALLRET_STACK_SIZE {0x40000};')
    name = 'Source/Windows/Common/CallRetStack.h'
    include(name)
    replace(name, '                                                 MEM_RESERVE | MEM_TOP_DOWN, PAGE_NOACCESS);',
            '                                                 MEM_RESERVE | MEM_TOP_DOWN, PAGE_NOACCESS);\n'
            '  if (!CallRetStackAlloc)\n'
            '    PES13FexHeapFailure("callret reserve", FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE);')
    replace(name,
            '  Thread->CallRetStackBase = reinterpret_cast<void*>(reinterpret_cast<uintptr_t>(CallRetStackAlloc) + FEXCore::Utils::FEX_PAGE_SIZE);\n'
            '  ::VirtualAlloc(Thread->CallRetStackBase, FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE, MEM_COMMIT, PAGE_READWRITE);',
            '  void* Base = reinterpret_cast<void*>(reinterpret_cast<uintptr_t>(CallRetStackAlloc) + FEXCore::Utils::FEX_PAGE_SIZE);\n'
            '  if (::VirtualAlloc(Base, FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE, MEM_COMMIT, PAGE_READWRITE) != Base) {\n'
            '    ::VirtualFree(const_cast<void*>(CallRetStackAlloc), 0, MEM_RELEASE);\n'
            '    PES13FexHeapFailure("callret commit", FEXCore::Core::InternalThreadState::CALLRET_STACK_SIZE);\n'
            '  }\n'
            '  Thread->CallRetStackBase = Base;')

    # rpmalloc's desktop geometry reserves 256 MiB plus the same amount for
    # alignment for its first tiny block. Native and guest mappings share the
    # Switch forwarder's low 4 GiB, whose holes cannot satisfy that request.
    # PES still exhausted VA with exact 32 MiB spans once DXVK started its
    # compiler threads. Use 8 MiB spans, 1 MiB medium / 8 MiB large pages and
    # pool blocks only up to 2 MiB; larger requests use the existing direct
    # PAGE_HUGE path. At least two maximum-sized blocks must fit: the pinned
    # page-full/free path does not support a size class with just one block.
    # Change the pinned submodule only in the isolated Horizon source tree.
    name = 'External/rpmalloc/rpmalloc/rpmalloc.c'
    replace(name, '#include "rpmalloc.h"',
            '#include "rpmalloc.h"\n#include "horizon_host.h"\n#include "horizon_heap.h"')
    replace(name, '#define MEDIUM_PAGE_SIZE_SHIFT 22',
            '#define MEDIUM_PAGE_SIZE_SHIFT PES13_FEX_HEAP_MEDIUM_PAGE_SHIFT')
    replace(name, '#define LARGE_PAGE_SIZE_SHIFT 26',
            '#define LARGE_PAGE_SIZE_SHIFT PES13_FEX_HEAP_LARGE_PAGE_SHIFT')
    replace(name, '#define SPAN_SIZE (256 * 1024 * 1024)',
            '#define SPAN_SIZE PES13_FEX_HEAP_SPAN_SIZE')
    replace(name, '#define LARGE_BLOCK_SIZE_LIMIT (8 * 1024 * 1024)',
            '#define LARGE_BLOCK_SIZE_LIMIT PES13_FEX_HEAP_LARGE_BLOCK_LIMIT')
    replace(name, '#define LARGE_SIZE_CLASS_COUNT 20',
            '#define LARGE_SIZE_CLASS_COUNT PES13_FEX_HEAP_LARGE_CLASS_COUNT')
    replace(name,
            'LCLASS(131072), LCLASS(163840), LCLASS(196608), LCLASS(229376),\n'
            '    LCLASS(262144), LCLASS(327680), LCLASS(393216), LCLASS(458752), LCLASS(524288)',
            'LCLASS(131072)')
    replace(name, 'PAGE_MEDIUM,  // 4MiB', 'PAGE_MEDIUM,  // 1MiB on Horizon')
    replace(name, 'PAGE_LARGE,   // 64MiB', 'PAGE_LARGE,   // 8MiB on Horizon')
    replace(name, '#define SPAN_MASK (~((uintptr_t)(SPAN_SIZE - 1)))',
            '#define SPAN_MASK (~((uintptr_t)(SPAN_SIZE - 1)))\n'
            '_Static_assert((SPAN_SIZE & (SPAN_SIZE - 1)) == 0, "span must be a power of two");\n'
            '_Static_assert(SPAN_SIZE >= LARGE_PAGE_SIZE && !(SPAN_SIZE % LARGE_PAGE_SIZE), "span/page geometry");\n'
            '_Static_assert(!(SPAN_SIZE % MEDIUM_PAGE_SIZE), "span/medium geometry");\n'
            '_Static_assert(SPAN_SIZE > RPMALLOC_MAX_ALIGNMENT, "aligned blocks must keep their span header");\n'
            '_Static_assert(MEDIUM_PAGE_SIZE >= 2 * MEDIUM_BLOCK_SIZE_LIMIT + PAGE_HEADER_SIZE, "multiple medium blocks required");\n'
            '_Static_assert(LARGE_PAGE_SIZE >= 2 * LARGE_BLOCK_SIZE_LIMIT + PAGE_HEADER_SIZE, "multiple blocks per page required");')
    # Wine's extended allocation can reserve the exact size at the required
    # alignment atomically. Keep the aligned-heap fix: no padding reservation.
    replace(name, '\tsize_t map_size = size + alignment;',
            '\tsize_t map_size = size;\n\t*offset = 0;')
    replace(name, '\tvoid* ptr =\n'
            '\t    VirtualAlloc(0, map_size, (os_huge_pages ? MEM_LARGE_PAGES : 0) | MEM_RESERVE | do_commit | MEM_TOP_DOWN, PAGE_READWRITE);',
            '\tvoid* ptr = PES13FexReserveHeap(map_size, alignment,\n'
            '\t    (os_huge_pages ? MEM_LARGE_PAGES : 0) | MEM_RESERVE | do_commit | MEM_TOP_DOWN);')
    replace(name, '\t\tsize_t padding = ((uintptr_t)ptr & (uintptr_t)(alignment - 1));',
            '\t\t// Any misaligned result would overrun the exact reservation.\n'
            '\t\tif ((uintptr_t)ptr & (uintptr_t)(alignment - 1))\n'
            '\t\t\tPES13FexHeapFailure("alignment", alignment);\n'
            '\t\tsize_t padding = ((uintptr_t)ptr & (uintptr_t)(alignment - 1));')
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
    # Resolve the writable view once per owned emission buffer. JIT code is
    # emitted to ordinary guarded scratch first; resolving every 4-byte store
    # scanned all CodeAlias slots and crossed PE/native even for identity maps.
    # Keep RX cursors/relocations and the old checked path outside this range.
    replace(name, '    Size = BaseSize;\n',
            '    Size = BaseSize;\n'
            '    WritableBase = Base && BaseSize\n'
            '      ? static_cast<uint8_t*>(PES13FexWriteAlias(Base, BaseSize)) : nullptr;\n')
    replace(name, '  uint64_t Size;\n', '  uint64_t Size;\n  uint8_t* WritableBase;\n')
    replace(name, '  template<typename T>\n  requires',
            '  void* Writable(void* Address, size_t Length) const {\n'
            '    const auto Target = reinterpret_cast<uintptr_t>(Address);\n'
            '    const auto Base = reinterpret_cast<uintptr_t>(BufferBase);\n'
            '    if (WritableBase && Target >= Base && Target - Base <= Size &&\n'
            '        Length <= Size - (Target - Base))\n'
            '      return WritableBase + (Target - Base);\n'
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

    name = 'Source/Windows/WOW64/Module.cpp'
    replace(name, '  PES13FexJitTimingInit();',
            '  PES13FexJitTimingInit();\n'
            '  PES13FexLog("[FEX3-EMIT] v1 cached writable buffer; bounded stores, RX cursors preserved");')

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
    replace(name, '      CTX->ClearCodeCache(ThreadState);\n      continue;',
            '      CTX->ClearCodeCache(ThreadState);\n'
            '      // A negotiated fallback may be smaller than one compiled block.\n'
            '      // Stop instead of endlessly rotating fresh caches. Compare total\n'
            '      // capacity, not remaining space: another compiler may append.\n'
            '      if (FEXCore::AlignUp(Size, 16) > CurrentCodeBuffer->UsableSize())\n'
            '        PES13FexCodeFailure("compiled block exceeds fresh cache", Size);\n'
            '      continue;')

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
    include(name)
    # On device the first 64 MiB buffer succeeds during boot, but growth to
    # 128 MiB after the intro begins fails to find both RW/RX aliases. FEX
    # then repeatedly falls back to 4 MiB buffers, invalidates lookup state,
    # and eventually cannot allocate even 2 MiB. Reserve 128 MiB during boot
    # while address space is open. The existing geometric fallback retains the
    # 64/32/16/8/4/2 MiB path if this larger early request cannot be mapped.
    replace(name, 'static constexpr size_t INITIAL_CODE_SIZE = 1024 * 1024 * 16;',
            'static constexpr size_t INITIAL_CODE_SIZE = 1024 * 1024 * 128;')
    replace(name, '    AllocateNew(INITIAL_CODE_SIZE);',
            '    AllocateNew(INITIAL_CODE_SIZE);\n'
            '    PES13FexPrimeCodeCache(INITIAL_CODE_SIZE);')
    replace(name, '  Ptr = static_cast<uint8_t*>(FEXCore::Allocator::VirtualAlloc(Size, true));\n'
                  '  LOGMAN_THROW_A_FMT(!!Ptr, "Couldn\'t allocate code buffer");',
            '  // Keep standard geometric growth when mappings fit. Horizon may\n'
            '  // lack a contiguous alias even for 16 MiB after DXVK starts:\n'
            '  // retry smaller NEW buffers down to 2 MiB, without resetting\n'
            '  // or releasing any live code buffer.\n'
            '  while (!(Ptr = static_cast<uint8_t*>(PES13FexTryAllocateCode(AllocatedSize)))) {\n'
            '    if (AllocatedSize <= 2 * 1024 * 1024)\n'
            '      PES13FexCodeFailure("executable cache allocation", AllocatedSize);\n'
            '    AllocatedSize = std::max<size_t>(AllocatedSize / 2, 2 * 1024 * 1024);\n'
            '  }\n'
            '  if (AllocatedSize != Size) PES13FexLogCodeFallback(Size, AllocatedSize);')
    replace(name, 'FEXCore::Allocator::VirtualName("FEXMemJIT", Ptr, Size);',
            'FEXCore::Allocator::VirtualName("FEXMemJIT", Ptr, AllocatedSize);')
    replace(name, 'FEXCore::Allocator::VirtualTHPControl(Ptr, Size,',
            'FEXCore::Allocator::VirtualTHPControl(Ptr, AllocatedSize,')
    start = original(name).index('  // Protect the last page of the allocated buffer')
    end = original(name).index('\n  if (ShouldBeNamed)', start)
    patched[name] = patched[name][:start] + (
        '  // Horizon CodeMemory permissions cannot be changed by Wine VirtualProtect.\n'
        '  // Allocate() still excludes the final page through UsableSize(). The\n'
        '  // temporary compilation buffer retains its separate real guard page.\n'
        '  // The host alias adapter also rejects writes across an allocation.\n') + patched[name][end:]

    # Optional disk-cache validation has its own grow-until-fit loop. It is
    # disabled in our profile, but a mapping fallback must not make it spin.
    name = 'FEXCore/Source/Interface/Core/CodeCache.cpp'
    include(name)
    replace(name, '  while (CachedCode.size_bytes() > NewCodeBuffer->UsableSize()) {\n'
                  '    ValidationCTX->ClearCodeCache(ValidationThread.get());\n'
                  '    NewCodeBuffer = ValidationCTX->GetLatest();',
            '  while (CachedCode.size_bytes() > NewCodeBuffer->UsableSize()) {\n'
            '    const auto PreviousUsableSize = NewCodeBuffer->UsableSize();\n'
            '    ValidationCTX->ClearCodeCache(ValidationThread.get());\n'
            '    NewCodeBuffer = ValidationCTX->GetLatest();\n'
            '    if (CachedCode.size_bytes() > NewCodeBuffer->UsableSize() &&\n'
            '        NewCodeBuffer->UsableSize() <= PreviousUsableSize)\n'
            '      PES13FexCodeFailure("validation cache cannot grow", CachedCode.size_bytes());')

    # Compile scratch is shared but upstream retains disowned buffers for five
    # seconds. PES creates enough workers to exhaust Horizon's guest VA while
    # idle IR/decode buffers remain pinned (16 + 8 MiB per recent compiler).
    # Keep the original capacities, retirement and fast reownership. Before
    # growing a pool, reclaim a suitable idle buffer with the existing atomic
    # ownership protocol. Return its current list node: reclaim must not itself
    # need a new rpmalloc span. A former client with FLAG_FREE never touches its
    # stale iterator, including when its destructor races with this transfer.
    name = 'FEXCore/include/FEXCore/Utils/ThreadPoolAllocator.h'
    include(name)
    # The fixed 16 MiB IR workspace must remain 16 MiB, but Wine's low guest
    # VM has no contiguous 16 MiB interval after the splash. Allocate only the
    # unguarded workspaces from libnx's already-reserved native heap. Guarded
    # temporary JIT buffers retain their Wine VirtualProtect path.
    data = original(name)
    begin = data.index('class PooledAllocatorVirtual final')
    end = data.index('class PooledAllocatorVirtualWithGuard final', begin)
    unguarded = data[begin:end]
    assert unguarded.count('FEXCore::Allocator::VirtualAlloc(Size)') == 1
    assert unguarded.count('FEXCore::Allocator::VirtualFree(Ptr, Size)') == 1
    unguarded = unguarded.replace('FEXCore::Allocator::VirtualAlloc(Size)',
                                  'PES13FexAllocateScratch(Size)')
    unguarded = unguarded.replace('auto Result = PES13FexAllocateScratch(Size);',
                                  'auto Result = PES13FexAllocateScratch(Size);\n'
                                  '    if (!Result) return nullptr;')
    unguarded = unguarded.replace('FEXCore::Allocator::VirtualFree(Ptr, Size)',
                                  'PES13FexReleaseScratch(Ptr)')
    patched[name] = data[:begin] + unguarded + data[end:]
    replace(name, '    // Need to allocate a new buffer, couldn\'t fit\n    auto Data = Alloc(Size);',
            '    // Horizon: consume idle scratch before increasing the pool footprint.\n'
            '    // AllocationMutex is held by ClaimBuffer. A concurrent reowner\n'
            '    // or unclaimer wins by changing the flag first; never steal OWNED.\n'
            '    for (auto it = ClaimedBuffers.begin(); it != ClaimedBuffers.end(); ++it) {\n'
            '      if ((*it)->Size < Size) continue;\n'
            '      ClientFlags Expected = ClientFlags::FLAG_DISOWNED;\n'
            '      if ((*it)->CurrentClientOwnedFlag->compare_exchange_strong(Expected, ClientFlags::FLAG_FREE)) {\n'
            '        // Do not access the old client flag again: it may be destroyed.\n'
            '        (*it)->CurrentClientOwnedFlag = nullptr;\n'
            '        return it;\n'
            '      }\n'
            '    }\n\n'
            '    // Need to allocate a new buffer, couldn\'t fit\n'
            '    auto Data = Alloc(Size);\n'
            '    if (!Data) PES13FexHeapFailure("compiler scratch", Size);')
    replace(name, '    auto Ptr = FEXCore::Allocator::VirtualAlloc(Size);\n    uintptr_t LastPageAddr',
            '    auto Ptr = FEXCore::Allocator::VirtualAlloc(Size);\n'
            '    if (!Ptr) return nullptr; // Never protect a page derived from NULL.\n'
            '    uintptr_t LastPageAddr')

    # The latest team-selection run exhausts low-4-GiB VM before Vulkan
    # allocation failure. FEX-private C/C++ heaps do not need guest mappings.
    # Keep WinAPI VirtualAlloc/guards unchanged, but route all CRT/container
    # allocation families together to the native heap (never mixed frees).
    name = 'Source/Windows/Common/CRT/Alloc.cpp'
    include(name)
    for old, new in (
        ('::rpcalloc(NumOfElements, SizeOfElements)', 'PES13FexHeapCalloc(NumOfElements, SizeOfElements)'),
        ('::rpfree(Memory)', 'PES13FexHeapFree(Memory)'),
        ('::rpmalloc(Size)', 'PES13FexHeapAlloc(Size, 16)'),
        ('::rprealloc(Memory, NewSize)', 'PES13FexHeapRealloc(Memory, NewSize)'),
        ('::rpaligned_alloc(Alignment, Size)', 'PES13FexHeapAlloc(Size, Alignment)'),
    ):
        replace(name, old, new, count=2 if old == '::rpfree(Memory)' else 1)
    name = 'Source/Windows/Common/CRT/CRT.cpp'
    for old in ('rpmalloc_initialize(nullptr);', 'rpmalloc_thread_initialize();', 'rpmalloc_thread_finalize();'):
        replace(name, old, '// Native FEX heap has process lifetime; no per-thread spans.')
    name = 'FEXCore/Source/Utils/AllocatorHooks.cpp'
    include(name)
    for old, new in (
        ('::rpmalloc(size)', 'PES13FexHeapAlloc(size, 16)'),
        ('::rpcalloc(n, size)', 'PES13FexHeapCalloc(n, size)'),
        ('::rpmemalign(align, s)', 'PES13FexHeapAlloc(s, align)'),
        ('::rpaligned_alloc(global_config.page_size, size)', 'PES13FexHeapAlloc(size, global_config.page_size)'),
        ('::rpposix_memalign(&ptr, a, s)', 'PES13FexHeapPosixAlign(&ptr, a, s)'),
        ('::rprealloc(ptr, size)', 'PES13FexHeapRealloc(ptr, size)'),
        ('::rpfree(ptr)', 'PES13FexHeapFree(ptr)'),
        ('::rpmalloc_usable_size(ptr)', 'PES13FexHeapUsableSize(ptr)'),
        ('::rpaligned_alloc(a, s)', 'PES13FexHeapAlloc(s, a)'),
    ):
        replace(name, old, new, count=2 if old == '::rpfree(ptr)' else 1)
    replace(name, '  *r = ptr;\n  return res;', '  if (!res) *r = ptr;\n  return res;')
    replace(name, '  rpmalloc_thread_initialize();', '  // No per-thread native heap setup.')

    from fex_compile_trace_patches import apply as apply_compile_trace
    apply_compile_trace(original, replace, project)

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
    for manifest in (Path(output), project / 'local/fex1/horizon-module/patches.json',
                     project / 'local/fex3/polling-v1/module/patches.json',
                     project / 'local/fex3/macos-module/patches.json',
                     project / 'local/fex3/stability-540p/module/patches.json',
                     project / 'local/fex3/jit-latency/module/patches.json',
                     project / 'local/fex3/dispatch-cache/module/patches.json',
                     project / 'local/fex2/module/patches.json',
                     project / 'local/fex3/smc-fix/module/patches.json',
                     project / 'local/fex3/memory-fix/module/patches.json',
                     project / 'local/fex3/guest-fault-trace/module/patches.json',
                     project / 'local/fex3/aligned-heap/module/patches.json',
                     project / 'local/fex3/compact-heap/module/patches.json',
                     project / 'local/fex3/compact-cache/module/patches.json',
                     project / 'local/fex3/scratch-reuse/module/patches.json',
                     project / 'local/fex3/fd-routing/module/patches.json',
                     project / 'local/fex3/jit-growth/module/patches.json',
                     project / 'local/fex3/small-cache/module/patches.json',
                     project / 'local/fex3/native-lookup/module/patches.json',
                     project / 'local/fex3/early-128/module/patches.json',
                     project / 'local/fex3/alias-perf/module/patches.json',
                     project / 'local/fex3/fast-native/module/patches.json',
                     project / 'local/fex3/final-3d/module/patches.json'):
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
