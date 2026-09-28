"""Run the linked native JIT host with modeled libnx kernel/allocator services.

The old jitCreate is also executed to reproduce a NULL alias selection becoming
kernel InvalidMemoryRange. This verifies failure ownership and alias publication,
not real Horizon address-space availability or native instruction execution.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from fex_reservations import Model as NativeModel, arm, reg


class JitModel(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.locks = set()
        self.backing = {}
        self.objects = {}
        self.next_backing = 0x60000000
        self.next_alias = 0x30000000
        self.next_handle = 100
        self.failure = None
        self.cleanup_failure = None
        self.find_index = 0
        self.allow_null_mapping = False
        self.null_maps = 0
        self.operations = []
        self.stages = []
        self.messages = []
        self.logger = self.data + 0x800
        self.host = self.call(self.symbols['pes13_fex_native_host'])
        self.call(self.symbols['pes13_fex_set_logger'], self.logger)

    def string(self, pointer):
        data = bytearray()
        while len(data) < 512:
            value = self.vm.mem_read(pointer + len(data), 1)[0]
            if not value:
                break
            data.append(value)
        return data.decode('utf-8')

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == self.logger:
            self.messages.append(self.string(vm.reg_read(reg(0))))
            self.ret()
        elif pc in {s.get('mutexLock'), s.get('virtmemLock')}:
            lock = 'allocation' if pc == s.get('mutexLock') else 'virtmem'
            assert lock not in self.locks
            self.locks.add(lock)
            self.ret()
        elif pc in {s.get('mutexUnlock'), s.get('virtmemUnlock')}:
            lock = 'allocation' if pc == s.get('mutexUnlock') else 'virtmem'
            assert lock in self.locks
            self.locks.remove(lock)
            self.ret()
        elif pc == s.get('envIsSyscallHinted'):
            assert vm.reg_read(reg(0)) in (0x4b, 0x4c)
            self.ret(self.failure != 'capabilities')
        elif pc in {s.get('aligned_alloc'), s.get('__libnx_aligned_alloc')}:
            alignment, length = [vm.reg_read(reg(i)) for i in range(2)]
            assert alignment == 4096 and length and not length & 4095
            self.find_index = 0
            if self.failure == 'backing':
                self.ret(0)
            else:
                address = self.next_backing
                self.next_backing += length + 4096
                self.backing[address] = length
                self.operations.append(('backing', address, length))
                self.ret(address)
        elif pc == s.get('free'):
            address = vm.reg_read(reg(0))
            if address:
                assert address in self.backing
                assert all(obj['source'] != address for obj in self.objects.values()), 'Freed live CodeMemory backing'
                del self.backing[address]
                self.operations.append(('free', address))
            self.ret()
        elif pc == s.get('svcCreateCodeMemory'):
            pointer, source, length = [vm.reg_read(reg(i)) for i in range(3)]
            assert self.backing[source] == length
            self.operations.append(('create', source, length))
            if self.failure == 'create':
                self.ret(0xdc01)
            else:
                handle = self.next_handle
                self.next_handle += 1
                self.objects[handle] = {'source': source, 'size': length, 'rw': 0, 'rx': 0}
                vm.mem_write(pointer, struct.pack('<I', handle))
                self.ret()
        elif pc == s.get('virtmemFindCodeMemory'):
            length, guard = [vm.reg_read(reg(i)) for i in range(2)]
            assert 'virtmem' in self.locks and guard == 4096
            stage = 'find-rw' if self.find_index == 0 else 'find-rx'
            self.find_index += 1
            if self.failure == stage:
                self.ret(0)
            else:
                address = self.next_alias
                self.next_alias += length + 4096
                self.ret(address)
        elif pc == s.get('svcControlCodeMemory'):
            handle, operation, address, length, permission = [vm.reg_read(reg(i)) for i in range(5)]
            obj = self.objects[handle]
            assert obj['size'] == length
            self.operations.append(('control', operation, address, length, permission))
            if operation in (0, 1):
                assert 'virtmem' in self.locks
                assert permission == (3 if operation == 0 else 5)
                if not address:
                    self.null_maps += 1
                    assert self.allow_null_mapping, 'NULL alias forwarded to kernel'
                    self.ret(0xdc01)
                    return
                stage = 'map-rw' if operation == 0 else 'map-rx'
                if self.failure == stage:
                    self.ret(0xdc01)
                else:
                    obj['rw' if operation == 0 else 'rx'] = address
                    self.ret()
            else:
                assert operation in (2, 3) and permission == 0
                key = 'rw' if operation == 2 else 'rx'
                assert address and obj[key] == address
                if self.cleanup_failure == 'unmap-' + key:
                    self.ret(0xd401)
                else:
                    obj[key] = 0
                    self.ret()
        elif pc == s.get('svcCloseHandle'):
            handle = vm.reg_read(reg(0))
            assert handle in self.objects
            assert not self.objects[handle]['rw'] and not self.objects[handle]['rx']
            self.operations.append(('close', handle))
            if self.cleanup_failure == 'close-handle':
                self.ret(0xd401)
            else:
                del self.objects[handle]
                self.ret()
        elif pc == s.get('snprintf'):
            dest, limit, fmt = [vm.reg_read(reg(i)) for i in range(3)]
            value = self.string(fmt)
            if 'stage=%s' in value:
                stage = self.string(vm.reg_read(reg(3)))
                self.stages.append(stage)
                value = 'stage=' + stage
            output = value.encode()[:limit - 1]
            vm.mem_write(dest, output + b'\0')
            self.ret(len(output))
        elif pc == s.get('memset'):
            dest, value, length = [vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest, bytes([value & 255]) * length)
            self.ret(dest)
        elif pc in {s.get('armDCacheClean'), s.get('armICacheInvalidate')}:
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def call(self, address, *args):
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate(args):
            self.vm.reg_write(reg(i), value & 0xffffffffffffffff)
        self.vm.emu_start(address, 0, count=100000)
        assert self.returned and not self.locks
        return self.vm.reg_read(reg(0))

    def callback(self, offset, *args):
        return self.call(self.uq(self.host + offset), *args)

    def allocate(self, size):
        return self.callback(16, size)

    def alias(self, address, size):
        return self.callback(32, address, size)

    def release(self, address):
        value = self.callback(24, address) & 0xffffffff
        return value if value < 0x80000000 else value - 0x100000000


def check_before(path):
    result = {}
    for stage in ('find-rw', 'find-rx'):
        model = JitModel(path)
        model.allow_null_mapping = True
        model.failure = stage
        rc = model.call(model.symbols['jitCreate'], model.data + 0x1000, 64 << 20)
        assert rc == 0xdc01 and model.null_maps == 1
        assert not model.objects and not model.backing
        result[stage] = {'null_kernel_maps': model.null_maps, 'result': hex(rc)}
    return result


def check_after(path):
    cases = 0
    model = JitModel(path)
    assert model.callback(56, 0) == 0
    scratch = model.callback(56, 16 << 20)
    assert scratch and scratch % 4096 == 0
    assert model.backing[scratch] == 16 << 20
    model.callback(64, scratch)
    assert scratch not in model.backing and not model.objects
    cases += 1
    for failure in ('capabilities', 'backing', 'create', 'find-rw', 'map-rw', 'find-rx', 'map-rx'):
        model = JitModel(path)
        model.failure = failure
        assert model.allocate(64 << 20) == 0
        assert model.stages == [failure]
        assert not model.objects and not model.backing and not model.null_maps
        # The failed slot is reusable once every acquired resource was released.
        model.failure = None
        rx = model.allocate(16 << 20)
        assert rx and model.alias(rx, 16 << 20) != rx
        assert model.release(rx) == 1 and not model.objects and not model.backing
        cases += 1
    for cleanup in ('unmap-rw', 'close-handle'):
        model = JitModel(path)
        model.failure, model.cleanup_failure = 'find-rx', cleanup
        assert model.allocate(64 << 20) == 0
        assert len(model.objects) == len(model.backing) == 1
        retained = dict(model.backing)
        model.failure = model.cleanup_failure = None
        rx = model.allocate(16 << 20)
        assert rx and model.release(rx) == 1
        assert model.backing == retained and len(model.objects) == 1
        assert not model.null_maps
        cases += 1
    model = JitModel(path)
    first = model.allocate(16384)
    second = model.allocate(16 << 20)
    first_rw = model.alias(first, 16384)
    second_rw = model.alias(second, 16 << 20)
    assert first_rw != first and second_rw != second and first_rw != second_rw
    assert model.alias(second + 4096, 4096) == second_rw + 4096
    assert model.alias(second + (16 << 20) - 1, 2) == 0
    assert model.alias(second - 1, 2) == 0
    assert model.alias(0x10000000, 16) == 0x10000000
    assert model.release(second + 4096) == -1
    model.failure = 'find-rx'
    assert model.allocate(64 << 20) == 0
    assert model.alias(first, 16384) == first_rw and model.alias(second, 16 << 20) == second_rw
    assert model.release(second) == 1 and model.alias(first, 16384) == first_rw
    assert model.release(first) == 1 and not model.objects and not model.backing
    assert model.release(first) == 0
    cases += 1
    model = JitModel(path)
    live = [model.allocate(16384) for _ in range(64)]
    assert all(live) and len(set(live)) == 64
    operations = len(model.operations)
    assert model.allocate(16384) == 0 and len(model.operations) == operations
    assert any('[FEX-JIT] no free slots' in message for message in model.messages)
    for address in live:
        assert model.release(address) == 1
    assert not model.objects and not model.backing
    cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = check_before(args.before)
    cases = check_after(args.elf)
    report = {'passed': True,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'before_native_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'before_null_alias_reproduction': before, 'cases': cases,
              'checks': ['Actual old libnx jitCreate forwards failed RW/RX address selection to kernel as address zero',
                         'Every failure stage is identified; new host never maps a NULL alias',
                         'Backing/handle/partial mapping cleanup permits safe retry after ordinary failures',
                         'Cleanup failure retains backing and quarantines slot; next allocation cannot reuse it',
                         'Successful Jit objects release through actual libnx jitClose',
                         'Existing aliases survive failed growth, preserve bounds, and release independently',
                         'Slot exhaustion is diagnosed without allocating or corrupting live objects',
                         'Native scratch uses a page-aligned 16 MiB host allocation and releases it'],
              'scope': 'Linked native ARM64 JIT host and libnx lifecycle; allocator/kernel/address-finder calls modeled. No assertion about actual device fragmentation or FPS.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
