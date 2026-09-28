"""Exercise delivered ARM64 compiler-scratch pool ownership and memory pressure.

Actual pool/client/list code runs in Unicorn. NT VM, container heap, locks and
clock are modeled; deterministic interleavings are not a Horizon stress test.
"""
from pathlib import Path
import argparse
import hashlib
import json

from unicorn import arm64_const as arm

from fex_alloc import PARAM, STACK, reg
from fex_lookup import LookupModel
from fex_memory import MIB


POOL = '_ZN7FEXCore5Utils24IntrusivePooledAllocator'
CLIENT = '_ZN7FEXCore5Utils29PoolBufferWithTimedRetirementIPNS_9X86Tables11DecodedInstELy5000ELy500EE'
CLAIM = CLIENT + '26ReownOrClaimBufferWithSizeENSt3__18optionalIyEE'
DISOWN = CLIENT + '19DelayedDisownBufferEv'
FREE_ALL = POOL + '14FreeAllBuffersEv'
CLAIM_IMPL = POOL + '15ClaimBufferImplEy'
VTABLE = '_ZTVN7FEXCore5Utils22PooledAllocatorVirtualE'
GUARD_ALLOC = '_ZN7FEXCore5Utils31PooledAllocatorVirtualWithGuard5AllocEy'
FREE, OWNED, DISOWNED = 0, 1, 3


class ScratchModel(LookupModel):
    def __init__(self, dll):
        self.lock_depth = 0
        self.lock_calls = 0
        self.pause_clock = 0
        self.paused = False
        self.cas_flag = None
        self.cas_replacement = OWNED
        self.cas_injections = 0
        super().__init__(dll)
        self.pool = PARAM + 0x2000
        self.vm.mem_write(self.pool, bytes(80))
        # Pinned libc++ std::list: prev/next sentinel and size. The virtual
        # allocator vtable is taken from the delivered image, not a stub.
        self.writeq(self.pool, self.symbols[VTABLE] + 16)
        for offset in (8, 32):
            self.writeq(self.pool + offset, self.pool + offset)
            self.writeq(self.pool + offset + 8, self.pool + offset)
        self.clients = []

    def hook(self, vm, pc, size, user):
        symbol = getattr(self, 'by_address', {}).get(pc, '')
        if symbol == '_ZNSt3__16chrono12steady_clock3nowEv':
            vm.reg_write(reg(0), self.clock)
            self.host_return()
            if self.pause_clock:
                self.pause_clock -= 1
                if not self.pause_clock:
                    self.paused = True
                    vm.emu_stop()
            return
        if symbol in ('_ZNSt3__15mutex4lockEv', '_ZNSt3__15mutex6unlockEv'):
            if symbol.endswith('4lockEv'):
                assert self.lock_depth == 0
                self.lock_depth += 1
                self.lock_calls += 1
            else:
                assert self.lock_depth == 1
                self.lock_depth -= 1
            self.host_return()
            return
        if self.cas_flag is not None:
            # Inject the competing client's winning transition immediately
            # before the real exclusive read in the pool's reclaim CAS.
            instruction = int.from_bytes(vm.mem_read(pc, 4), 'little')
            if instruction & 0xfffffc00 == 0x885ffc00:
                source = (instruction >> 5) & 31
                address = vm.reg_read(reg(source)) if source != 31 else vm.reg_read(arm.UC_ARM64_REG_SP)
                if address == self.cas_flag and pc >= self.symbols[CLAIM_IMPL]:
                    vm.mem_write(address, self.cas_replacement.to_bytes(4, 'little'))
                    self.cas_flag = None
                    self.cas_injections += 1
        super().hook(vm, pc, size, user)

    def invoke(self, name, *args):
        self.trapped = False
        self.paused = False
        for index in range(8):
            self.vm.reg_write(reg(index), args[index] if index < len(args) else 0)
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK + 0x3f000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.emu_start(self.symbols[name], self.stop, count=500000)
        assert self.trapped or self.paused or self.vm.reg_read(arm.UC_ARM64_REG_PC) == self.stop, name
        return self.vm.reg_read(reg(0))

    def client(self, amount):
        address = PARAM + 0x3000 + len(self.clients) * 0x80
        assert address + 48 < PARAM + 0xf000
        self.vm.mem_write(address, bytes(48))
        self.writeq(address, self.pool)
        self.writeq(address + 8, amount)
        self.clients.append(address)
        return address

    def flag(self, client):
        return int.from_bytes(self.vm.mem_read(client + 24, 4), 'little')

    def claim(self, client, amount=None):
        pointer = self.invoke(CLAIM, client, amount or 0, int(amount is not None))
        if not self.trapped:
            assert self.flag(client) == OWNED
            assert self.lock_depth == 0
        return pointer

    def disown(self, client):
        assert self.flag(client) == OWNED
        self.invoke(DISOWN, client)
        if not self.paused:
            assert self.flag(client) in (FREE, DISOWNED)
            assert self.lock_depth == 0

    def buffer(self, client):
        return self.readq(self.readq(client + 16) + 16)

    def counts(self):
        return self.readq(self.pool + 24), self.readq(self.pool + 48)

    def scratch_regions(self):
        return {**self.regions, **self.native_regions}

    def cleanup(self):
        # Context teardown requires stopped clients. FreeAllBuffers is the
        # actual allocator destructor's cleanup, so do not touch clients again.
        self.invoke(FREE_ALL, self.pool)
        assert not self.trapped and not self.scratch_regions() and not self.allocations
        assert self.counts() == (0, 0)


def pressure(dll, target=32):
    model = ScratchModel(dll)
    live = []
    null_published = False
    for _ in range(target):
        client = model.client(16 * MIB)
        pointer = model.claim(client)
        if model.trapped:
            break
        if not pointer:
            null_published = True
            break
        live.append(client)
        model.disown(client)
    result = {'clients_served': len(live), 'reserved_bytes': sum(model.scratch_regions().values()),
              'allocations': len(model.scratch_regions()), 'null_published': null_published,
              'stopped': model.trapped}
    # The old DLL's null allocation cannot be freed through the model NT API;
    # retain its state to prove the failure instead of pretending cleanup passed.
    if not null_published and not model.trapped:
        model.cleanup()
    return result


def checks(dll):
    results = []
    model = ScratchModel(dll)
    first, second = model.client(16*MIB), model.client(16*MIB)
    pointer = model.claim(first)
    if model.abi == 2:
        assert not model.regions and len(model.native_regions) == 1
        assert pointer in model.native_regions and not pointer & 4095
    model.vm.mem_write(pointer, b'owned compiler')
    other = model.claim(second)
    assert other != pointer and len(model.scratch_regions()) == 2
    assert bytes(model.vm.mem_read(pointer, 14)) == b'owned compiler'
    model.disown(first)
    old_iterator = model.readq(first + 16)
    old_allocations = dict(model.allocations)
    third = model.client(16*MIB)
    assert model.claim(third) == pointer
    assert model.flag(first) == FREE and model.flag(second) == OWNED
    assert model.readq(third + 16) == old_iterator
    assert model.allocations == old_allocations  # No list allocation on reclaim.
    assert model.readq(model.buffer(third) + 24) == third + 24
    model.cleanup()
    results.append('two active compilers remain isolated; native scratch avoids Wine VM; disowned reuse preserves iterator')

    model = ScratchModel(dll)
    small, large = model.client(MIB), model.client(16*MIB)
    psmall = model.claim(small)
    model.disown(small)
    plarge = model.claim(large)
    assert plarge != psmall and model.flag(small) == DISOWNED
    model.disown(large)
    request = model.client(8*MIB)
    assert model.claim(request) == plarge
    assert model.vm.reg_read(reg(1)) == 16*MIB
    assert model.flag(small) == DISOWNED and model.flag(large) == FREE
    model.cleanup()
    results.append('undersized disowned buffers are skipped; oversized buffers preserve their actual allocation size')

    for competing_state in (OWNED, FREE):
        model = ScratchModel(dll)
        old, new = model.client(16*MIB), model.client(16*MIB)
        oldptr = model.claim(old)
        model.disown(old)
        old_buffer = model.buffer(old)
        model.cas_flag = old + 24
        model.cas_replacement = competing_state
        newptr = model.claim(new)
        assert model.cas_injections == 1 and newptr != oldptr
        assert model.flag(old) == competing_state and model.flag(new) == OWNED
        assert model.readq(old_buffer + 24) == old + 24
        # FREE models UnclaimBuffer's exchange before it acquires the held
        # allocator mutex. Reclaim must leave its iterator for that caller.
        model.cleanup()
    results.append('competing reown or retirement wins at the real CAS exclusive read; reclaim loser leaves old metadata untouched')

    model = ScratchModel(dll)
    old, new = model.client(16*MIB), model.client(16*MIB)
    oldptr = model.claim(old)
    model.clock = 6_000_000_000
    model.pause_clock = 2
    model.disown(old)
    assert model.paused and model.flag(old) == DISOWNED
    saved_context = model.vm.context_save()
    saved_stack = bytes(model.vm.mem_read(STACK, 0x40000))
    assert model.claim(new) == oldptr and model.flag(old) == FREE
    new_buffer = model.buffer(new)
    model.vm.mem_write(STACK, saved_stack)
    model.vm.context_restore(saved_context)
    resume = model.vm.reg_read(arm.UC_ARM64_REG_PC)
    model.vm.emu_start(resume, model.stop, count=500000)
    assert model.vm.reg_read(arm.UC_ARM64_REG_PC) == model.stop
    assert model.flag(old) == FREE and model.flag(new) == OWNED
    assert model.readq(new_buffer + 24) == new + 24
    assert model.counts() == (0, 1)
    model.cleanup()
    results.append('old delayed retirement resumed after reclaim sees FREE and cannot unclaim the new owner')

    model = ScratchModel(dll)
    first = model.client(16*MIB)
    ptr = model.claim(first)
    model.clock = 6_000_000_000
    model.disown(first)
    assert model.flag(first) == FREE and model.counts() == (1, 0)
    second = model.client(16*MIB)
    assert model.claim(second) == ptr and model.counts() == (0, 1)
    model.cleanup()
    results.append('ordinary five-second retirement/unclaimed reuse and full context cleanup remain valid')

    for amount in (8*MIB, 16*MIB):
        model = ScratchModel(dll)
        expected = None
        for wave in range(12):
            clients = [model.client(amount) for _ in range(4)]
            pointers = {model.claim(client) for client in clients}
            assert len(pointers) == 4
            if expected is None:
                expected = pointers
            assert pointers == expected and len(model.scratch_regions()) == 4
            assert all(model.flag(client) == OWNED for client in clients)
            for client in clients:
                model.disown(client)
            model.clock += 10_000_000  # All twelve waves remain below 5 s.
        assert sum(model.scratch_regions().values()) == 4*amount
        model.cleanup()
    results.append('twelve waves of four overlapping compiler clients keep exactly four full-capacity 8 MiB or 16 MiB buffers')

    for live_count in (0, 2):
        model = ScratchModel(dll)
        for _ in range(live_count):
            model.claim(model.client(16*MIB))
        existing = model.counts()
        model.fail_allocations = True
        failing = model.client(16*MIB)
        model.claim(failing)
        assert model.trapped and model.flag(failing) == FREE
        assert model.counts() == existing
        assert any('compiler scratch' in line for line in model.logs)
    results.append('real OOM stops before publishing a null scratch buffer with zero or two owned buffers')

    model = ScratchModel(dll)
    model.fail_allocations = True
    assert model.invoke(GUARD_ALLOC, model.pool, MIB) == 0 and not model.trapped
    assert not any(name == 'NtProtectVirtualMemory' for name, _ in model.calls)
    results.append('guard allocator returns allocation failure before protecting a null-derived address')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, after = pressure(args.before), pressure(args.dll)
    assert before['clients_served'] < 32 and before['null_published']
    assert after['clients_served'] == 32 and after['reserved_bytes'] == 16*MIB
    assert not after['stopped'] and not after['null_published']
    results = checks(args.dll)
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'pressure_before': before, 'pressure_after': after,
              'checks': results, 'on_device_tested': False,
              'scope': 'Actual ARM64 scratch pool/client/list instructions; modeled NT VM, container heap, clock, locks and deterministic races'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
