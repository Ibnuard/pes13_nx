"""Exercise the delivered ARM64 shared-code cache and its host allocation ABI.

The real constructor, geometric growth, atomic append, shared_ptr ownership,
signal references and destructors run in Unicorn. Host mappings, VM advice,
container heap and configuration are modeled. The append test substitutes
cache invalidation with the real backend buffer rollover; lookup invalidation
is covered separately. This is not a Horizon kernel or whole-game test.
"""
from pathlib import Path
import argparse
import hashlib
import json

from unicorn import arm64_const as arm

from fex_alloc import PARAM, STUBS, reg
from fex_lookup import LookupModel
from fex_memory import MIB, PAGE


CODE = '_ZN7FEXCore3CPU10CodeBuffer'
MANAGER = '_ZN7FEXCore3CPU23SharedCodeBufferManager'
BACKEND = '_ZN7FEXCore3CPU10CPUBackend'
APPEND = '_ZN7FEXCore3CPU12Arm64JITCore31AllocateCodeBufferInSharedCacheEy'
CLEAR = '_ZN7FEXCore7Context11ContextImpl14ClearCodeCacheEPNS_4Core19InternalThreadStateEb'


class CodeModel(LookupModel):
    def __init__(self, dll, maximum=128*MIB):
        self.maximum = maximum
        self.code_requests = []
        self.code = {}
        self.code_next = 0x80000000
        self.released = []
        self.advice = []
        self.backends = []
        self.rollovers = 0
        self.fill_next_rollover = False
        self.rollover_return = None
        self.validation_reached_compile = False
        self.testing_validation = False
        super().__init__(dll)
        self.manager = PARAM + 0x2000
        self.writeq(self.symbols['_ZN7FEXCore9Allocator11VirtualNameE'], STUBS+0xb000)
        self.writeq(self.symbols['_ZN7FEXCore9Allocator17VirtualTHPControlE'], STUBS+0xb100)
        self.call(MANAGER+'C2Ev', self.manager)
        assert not self.trapped

    def host_callbacks(self):
        return STUBS+0xd800, STUBS+0xd000, self.alias, self.stop, self.logger

    def hook(self, vm, pc, size, user):
        a = [vm.reg_read(reg(i)) for i in range(4)]
        symbol = getattr(self, 'by_address', {}).get(pc, '')
        if pc == STUBS+0xd800:
            amount = a[0]
            self.code_requests.append(amount)
            address = 0
            if 0 < amount <= self.maximum:
                assert amount % PAGE == 0
                address = self.code_next
                self.code_next += amount + PAGE
                vm.mem_map(address, amount)
                self.code[address] = amount
            vm.reg_write(reg(0), address)
            self.host_return()
            return
        if pc == STUBS+0xd000:
            amount = self.code.pop(a[0], None)
            if amount is not None:
                self.released.append((a[0], amount))
                vm.mem_unmap(a[0], amount)
            vm.reg_write(reg(0), int(amount is not None))
            self.host_return()
            return
        if pc in (STUBS+0xb000, STUBS+0xb100):
            address, amount = (a[1], a[2]) if pc == STUBS+0xb000 else (a[0], a[1])
            if address in self.code:
                assert self.code[address] == amount, 'VM advice exceeded actual allocation'
                self.advice.append((address, amount))
            else:
                # GuestToHostMap also names its ordinary container pages.
                allocation = self.allocation_at(address)
                assert allocation and address+amount <= sum(allocation)
            self.host_return()
            return
        if symbol == '_ZN7FEXCore9Allocator13aligned_allocEyy':
            vm.reg_write(reg(0), self.heap_alloc(a[1], a[0]))
            self.host_return()
            return
        if symbol == '_ZN7FEXCore9Allocator12aligned_freeEPv':
            if a[0]:
                self.allocations.pop(a[0])
            self.host_return()
            return
        if symbol == CLEAR:
            # Preserve the actual buffer manager, old-reference handling and
            # constructor. Model only cache invalidation/call-ret clearing.
            backend = next(b for b in self.backends if self.readq(b+8) == a[1])
            self.rollovers += 1
            if self.fill_next_rollover:
                self.rollover_return = (vm.reg_read(reg(30)), backend)
                self.fill_next_rollover = False
            vm.reg_write(reg(0), backend)
            vm.reg_write(arm.UC_ARM64_REG_PC, self.symbols[BACKEND+'26AcquireNewSharedCodeBufferEv'])
            return
        if self.testing_validation and symbol.startswith('_ZN6LogMan3Msg8MFmtImpl'):
            # The validation loop's informational message does not affect it.
            self.host_return()
            return
        if self.testing_validation and symbol == '_ZN7FEXCore7Context11ContextImpl11CompileCodeEPNS_4Core19InternalThreadStateEyy':
            # Terminal observation: the real validation capacity loop was
            # passed. Do not claim to test validation's unrelated recompilation.
            self.validation_reached_compile = True
            vm.reg_write(arm.UC_ARM64_REG_PC, self.stop)
            vm.emu_stop()
            return
        if self.rollover_return and pc == self.rollover_return[0]:
            # Another compiler consumes the fresh cache before this thread
            # resumes. Capacity checks must not mistake remaining-space
            # exhaustion for an oversized indivisible block.
            buffer = self.readq(self.rollover_return[1]+16)
            self.writeq(buffer+32, self.readq(buffer+16))
            self.rollover_return = None
        super().hook(vm, pc, size, user)

    def create_code(self, requested, named=True):
        obj = PARAM + 0x2800
        self.vm.mem_write(obj, bytes(40))
        self.call(CODE+'C2Eyb', obj, requested, named)
        return obj

    def check_code(self, obj, expected):
        base = self.readq(obj+8)
        assert self.readq(obj+24) == expected
        assert self.readq(obj+16) == base+expected-PAGE
        assert self.readq(obj+32) == base
        assert self.readq(obj) != 0 and self.code[base] == expected
        assert not self.trapped
        return base

    def backend(self):
        # Pinned CPUBackend prefix; derived fields are zero unless used below.
        # The real lifecycle routines operate on these actual shared_ptrs.
        slot = PARAM+0x4000+len(self.backends)*0x1000
        thread, frame = slot+0x200, slot+0x400
        self.vm.mem_write(slot, bytes(0x1000))
        self.writeq(slot+8, thread)
        self.writeq(slot+56, self.manager)
        self.writeq(thread, frame)
        self.vm.reg_write(reg(8), slot+16)
        self.call(MANAGER+'9GetLatestEv', self.manager)
        self.backends.append(slot)
        return slot

    def signal(self, backend, active):
        frame = self.readq(self.readq(backend+8))
        self.vm.mem_write(frame+0x5d0, int(active).to_bytes(4, 'little'))

    def grow(self, backend):
        return self.call(BACKEND+'26AcquireNewSharedCodeBufferEv', backend)

    def append(self, backend, length):
        self.call(APPEND, backend, length)
        return self.vm.reg_read(reg(0)), self.vm.reg_read(reg(1))

    def cleanup(self):
        for backend in self.backends:
            self.call(BACKEND+'D2Ev', backend)
        self.call(MANAGER+'D2Ev', self.manager)
        assert not self.trapped and not self.code and not self.allocations

    def validation_capacity(self, length):
        backend = self.backend()
        cache, guest_set, host_set, node = (PARAM+x for x in (0xa000, 0xa100, 0xa200, 0xa300))
        self.writeq(cache+0x28, self.manager-8)  # ContextImpl's manager base subobject.
        self.writeq(cache+0x30, self.readq(backend+8))
        self.writeq(host_set, node)
        self.writeq(node+0x20, 4)  # sizeof(JITCodeHeader), so cached-span offset is zero.
        self.writeq(guest_set, node)
        self.writeq(guest_set+16, 1)
        name = self.method('9CodeCache8Validate')
        self.testing_validation = True
        self.call(name, cache, PARAM+0xa400, guest_set, host_set, PARAM+0xb000, length)


def before_check(path):
    model = CodeModel(path, maximum=32*MIB)
    obj = model.create_code(64*MIB)
    assert model.trapped and model.code_requests == [64*MIB]
    assert model.readq(obj) == 0 and not model.code
    return {'dll_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'requested_bytes': model.code_requests, 'stopped_without_fallback': True}


def checks(path):
    results = []
    model = CodeModel(path)
    backend = model.backend()
    initial = model.readq(backend+16)
    base = model.check_code(initial, 128*MIB)
    assert model.code_requests == [128*MIB]
    assert model.append(backend, 32*MIB) == (base, base)
    assert model.rollovers == 0 and model.readq(initial+32) == base+32*MIB
    model.cleanup()
    results.append({'scenario': 'initial_128_MiB_reserves_32_MiB_without_rollover'})

    model = CodeModel(path, maximum=32*MIB)
    backend = model.backend()
    model.check_code(model.readq(backend+16), 32*MIB)
    assert model.code_requests == [128*MIB, 64*MIB, 32*MIB] and not model.trapped
    model.cleanup()
    results.append({'scenario': 'initial_128_MiB_falls_back_to_32_MiB_early'})

    for requested, maximum, attempts, actual in (
        (16, 128, [16], 16), (64, 128, [64], 64),
        (64, 32, [64, 32], 32), (128, 16, [128, 64, 32, 16], 16),
        (64, 8, [64, 32, 16, 8], 8),
        (64, 2, [64, 32, 16, 8, 4, 2], 2),
    ):
        model = CodeModel(path, maximum=maximum*MIB)
        obj = model.create_code(requested*MIB)
        base = model.check_code(obj, actual*MIB)
        assert model.code_requests == [amount*MIB for amount in attempts]
        assert model.advice == [(base, actual*MIB)]*2
        fallback_logs = [line for line in model.logs if '[FEX3-CODE] fallback ' in line]
        assert len(fallback_logs) == int(requested != actual)
        if fallback_logs:
            assert f'requested=0x{requested*MIB:016x} actual=0x{actual*MIB:016x}' in fallback_logs[0]
        model.call(CODE+'D2Ev', obj)
        assert model.released == [(base, actual*MIB)]
        model.cleanup()
        results.append({'scenario': f'constructor_{requested}_to_{actual}_MiB', 'attempts_MiB': attempts})

    model = CodeModel(path, maximum=0)
    obj = model.create_code(64*MIB)
    assert model.trapped and model.code_requests == [64*MIB, 32*MIB, 16*MIB, 8*MIB, 4*MIB, 2*MIB]
    assert model.readq(obj) == 0 and not model.code and not model.allocations
    assert any('STOP executable cache allocation' in line for line in model.logs)
    results.append({'scenario': 'all_sizes_unavailable_stops_before_lookup_or_publication'})

    model = CodeModel(path, maximum=32*MIB)
    assert model.call('PES13FexTryAllocateCode', 64*MIB) == 0 and not model.trapped
    model.call('PES13FexAllocateCode', 64*MIB)
    assert model.trapped and model.code_requests == [64*MIB, 64*MIB]
    results.append({'scenario': 'fixed_allocation_remains_strict_try_allocation_nonfatal'})

    model = CodeModel(path, maximum=32*MIB)
    first, second = model.backend(), model.backend()
    old_obj = model.readq(first+16)
    old_base = model.readq(old_obj+8)
    model.vm.mem_write(old_base, b'live code generation')
    model.signal(first, True)
    generation32 = model.grow(first)
    base32 = model.check_code(generation32, 32*MIB)
    fallback_obj = model.grow(first)
    fallback_base = model.check_code(fallback_obj, 32*MIB)
    assert fallback_base != base32 and not model.released
    assert bytes(model.vm.mem_read(old_base, 20)) == b'live code generation'
    assert model.readq(second+16) == old_obj
    # Signal references preserve both old generations despite further growth.
    assert model.readq(first+40)-model.readq(first+32) == 32
    model.call(BACKEND+'D2Ev', second)
    model.backends.remove(second)
    assert old_base in model.code and base32 in model.code
    model.signal(first, False)
    model.grow(first)
    assert old_base not in model.code and base32 not in model.code and fallback_base not in model.code
    assert len(model.code) == 1
    model.maximum = 128*MIB
    sizes = []
    for _ in range(3):
        buffer = model.grow(first)
        sizes.append(model.readq(buffer+24)//MIB)
    assert sizes == [64, 128, 128], sizes
    model.cleanup()
    results.append({'scenario': 'fresh_fallback_preserves_other_threads_and_signals_until_natural_release',
                    'growth_after_pressure_lifts_MiB': sizes})

    model = CodeModel(path, maximum=16*MIB)
    backend = model.backend()
    obj = model.readq(backend+16)
    base = model.readq(obj+8)
    assert model.append(backend, 123) == (base, base)
    assert model.readq(obj+32) == base+128
    assert model.append(backend, 16*MIB-PAGE-128) == (base, base+128)
    assert model.readq(obj+32) == model.readq(obj+16)
    new_base, allocated = model.append(backend, 16)
    assert new_base != base and allocated == new_base
    assert not model.trapped and model.rollovers == 1
    assert model.code_requests == [128*MIB, 64*MIB, 32*MIB, 16*MIB, 32*MIB, 16*MIB]
    model.cleanup()
    results.append({'scenario': 'aligned_append_reserves_last_page_and_rolls_to_fresh_fallback'})

    model = CodeModel(path, maximum=16*MIB)
    backend = model.backend()
    model.append(backend, 16*MIB-PAGE+1)
    assert model.trapped and model.rollovers == 1
    assert any('STOP compiled block exceeds fresh cache' in line for line in model.logs)
    assert model.code_requests == [128*MIB, 64*MIB, 32*MIB, 16*MIB, 32*MIB, 16*MIB]
    model.cleanup()
    results.append({'scenario': 'oversized_compiled_block_stops_after_one_rollover'})

    model = CodeModel(path, maximum=16*MIB)
    backend = model.backend()
    obj = model.readq(backend+16)
    model.writeq(obj+32, model.readq(obj+16))
    model.fill_next_rollover = True
    base, allocated = model.append(backend, 16)
    assert allocated == base and not model.trapped and model.rollovers == 2
    model.cleanup()
    results.append({'scenario': 'concurrent_append_exhaustion_is_not_mistaken_for_oversized_block'})

    for maximum, length, expected_requests, stopped in (
        (16, 24, [128, 64, 32, 16, 32, 16], True),
        (32, 48, [128, 64, 32, 64, 32], True),
        (64, 48, [128, 64], False),
    ):
        model = CodeModel(path, maximum=maximum*MIB)
        model.validation_capacity(length*MIB)
        assert model.code_requests == [amount*MIB for amount in expected_requests]
        assert model.trapped == stopped
        assert model.validation_reached_compile == (not stopped)
        assert any('STOP validation cache cannot grow' in line for line in model.logs) == stopped
        results.append({'scenario': f'validation_capacity_{length}_MiB_limit_{maximum}_MiB',
                        'attempts_MiB': expected_requests, 'stopped_without_progress': stopped})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'native_not_tested': True, 'hardware_tested': False,
              'model_scope': 'Actual ARM64 FEX cache constructor/growth/append/reference lifecycle and validation capacity loop; modeled host mappings, VM advice, heap/config and cache invalidation. Validation stops at recompilation entry.'}
    if args.before:
        result['before'] = before_check(args.before)
    result['scenarios'] = checks(args.dll)
    result['scenario_count'] = len(result['scenarios'])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
