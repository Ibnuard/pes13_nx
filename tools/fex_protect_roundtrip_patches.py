"""Preserve writable guest permissions across FEX MTRACK/VirtualProtect.

Apply to the delivered FEX source, not to game code. Only the first page is
untrapped before NtProtectVirtualMemory: Windows returns that page's old
protection. The code lock spans the native operation so compilation cannot
reapply an RX trap before that old protection is read.
"""


def apply(source):
    changed = set()

    def edit(name, replacements):
        path = source / name
        data = path.read_text()
        for old, new in replacements:
            assert data.count(old) == 1, (name, old[:100], data.count(old))
            data = data.replace(old, new)
        path.write_text(data)
        changed.add(name)

    signature = 'void HandleMemoryProtectionNotification(uint64_t Address, uint64_t Size, ULONG Prot);'
    edit('Source/Windows/Common/InvalidationTracker.h', [
        (signature, 'void HandleMemoryProtectionNotification(uint64_t Address, uint64_t Size, ULONG Prot, bool CodeLockHeld = false);\n'
         '  // Paired by WOW64 with ThreadCreationMutex held across the native syscall.\n'
         '  void BeginGuestProtectionChange(uint64_t Address, uint64_t Size);\n'
         '  void EndGuestProtectionChange(uint64_t Address, uint64_t Size, ULONG Prot, ULONG Status);'),
        ('  bool SMCDetectionDisabled {false};',
         '  uint64_t GuestProtectRestorePage {}; // ThreadCreationMutex + CodeInvalidationMutex\n'
         '  ULONG GuestProtectRestoreTrap {};\n'
         '  bool SMCDetectionDisabled {false};')])

    methods = r'''
void InvalidationTracker::BeginGuestProtectionChange(uint64_t Address, uint64_t Size) {
  CTX.GetCodeInvalidationMutex().lock();
  GuestProtectRestoreTrap = 0;
  if (!Size || Address > std::numeric_limits<uint64_t>::max() - (Size - 1)) {
    return;
  }

  ULONG TrapProt, UntrapProt;
  {
    std::shared_lock Lock(IntervalsLock);
    if (SMCDetectionDisabled || !RWXIntervals.Query(Address).Enclosed) {
      return;
    }
    TrapProt = GetTrapProt(Address);
    UntrapProt = GetUntrapProt(Address);
  }

  MEMORY_BASIC_INFORMATION Info {};
  if (NtQueryVirtualMemory(NtCurrentProcess(), reinterpret_cast<void*>(Address), MemoryBasicInformation,
                           &Info, sizeof(Info), nullptr) || Info.State != MEM_COMMIT || Info.Protect != TrapProt) {
    // Only remove our exact trap. Never strip PAGE_GUARD, NOACCESS, or an
    // unrelated protection, and never turn an untracked RX page writable.
    return;
  }

  const auto Page = Address & FEXCore::Utils::FEX_PAGE_MASK;
  InvalidateIntervalInternalLocked(Page, FEXCore::Utils::FEX_PAGE_SIZE);
  void* TmpAddress = reinterpret_cast<void*>(Page);
  SIZE_T TmpSize = FEXCore::Utils::FEX_PAGE_SIZE;
  ULONG OldProt;
  const auto Status = NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, UntrapProt, &OldProt);
  if (Status) {
    PES13FexLogSMCProtectFailure(Page, TmpSize, UntrapProt, Status);
    return;
  }
  GuestProtectRestorePage = Page;
  GuestProtectRestoreTrap = TrapProt;
  static unsigned Reports {};
  if (Reports++ < 16) PES13FexLog("[FEX-PROTECT] v1 restored tracked writable permission before guest protect");
}

void InvalidationTracker::EndGuestProtectionChange(uint64_t Address, uint64_t Size, ULONG Prot, ULONG Status) {
  if (!Status) {
    // Keep the RX demotion optimization: an explicit guest RX request still
    // removes writable tracking. Only the old protection returned by the
    // native syscall is corrected; no read-only guest write is authorized.
    HandleMemoryProtectionNotification(Address, Size, Prot, true);
  } else if (GuestProtectRestoreTrap) {
    // A rejected guest request must not leave our temporary untrap behind.
    void* TmpAddress = reinterpret_cast<void*>(GuestProtectRestorePage);
    SIZE_T TmpSize = FEXCore::Utils::FEX_PAGE_SIZE;
    ULONG OldProt;
    const auto RestoreStatus = NtProtectVirtualMemory(NtCurrentProcess(), &TmpAddress, &TmpSize, GuestProtectRestoreTrap, &OldProt);
    if (RestoreStatus) PES13FexLogSMCProtectFailure(GuestProtectRestorePage, TmpSize, GuestProtectRestoreTrap, RestoreStatus);
  }
  GuestProtectRestoreTrap = 0;
  CTX.GetCodeInvalidationMutex().unlock();
}

'''
    edit('Source/Windows/Common/InvalidationTracker.cpp', [
        ('void InvalidationTracker::HandleMemoryProtectionNotification(uint64_t Address, uint64_t Size, ULONG Prot) {',
         'void InvalidationTracker::HandleMemoryProtectionNotification(uint64_t Address, uint64_t Size, ULONG Prot, bool CodeLockHeld) {'),
        ('    InvalidateIntervalInternal(AlignedBase, AlignedSize);\n  }\n}\n\nvoid InvalidationTracker::HandleProcessExecuteFlagsChange',
         '    if (CodeLockHeld) InvalidateIntervalInternalLocked(AlignedBase, AlignedSize);\n'
         '    else InvalidateIntervalInternal(AlignedBase, AlignedSize);\n  }\n}\n' + methods +
         'void InvalidationTracker::HandleProcessExecuteFlagsChange')])

    old = '''void BTCpuNotifyMemoryProtect(void* Address, SIZE_T Size, ULONG NewProt, BOOL After, ULONG Status) {
  if (!After) {
    ThreadCreationMutex.lock();
  } else {
    if (!Status) {
      InvalidationTracker->HandleMemoryProtectionNotification(reinterpret_cast<uint64_t>(Address), static_cast<uint64_t>(Size), NewProt);
    }
    ThreadCreationMutex.unlock();
  }
}'''
    new = '''void BTCpuNotifyMemoryProtect(void* Address, SIZE_T Size, ULONG NewProt, BOOL After, ULONG Status) {
  if (!After) {
    ThreadCreationMutex.lock();
    InvalidationTracker->BeginGuestProtectionChange(reinterpret_cast<uint64_t>(Address), static_cast<uint64_t>(Size));
  } else {
    InvalidationTracker->EndGuestProtectionChange(reinterpret_cast<uint64_t>(Address), static_cast<uint64_t>(Size), NewProt, Status);
    ThreadCreationMutex.unlock();
  }
}'''
    edit('Source/Windows/WOW64/Module.cpp', [
        (old, new),
        ('  PES13FexLog("[FEX2] core init");',
         '  PES13FexLog("[FEX-PROTECT] kit6 v1 guest protection round-trip; normal optimization");\n'
         '  PES13FexLog("[FEX2] core init");')])
    return changed
