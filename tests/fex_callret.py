"""Execute the linked ARM64 call/return prediction-stack lifecycle and recovery.

NT memory services are modeled with inaccessible guard pages. The push/pop
stress executes the same paired access form emitted by FEX BranchOps.cpp;
it is not a full guest-CPU or Horizon exception-delivery test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import UcError, UC_ERR_READ_PROT, UC_ERR_WRITE_PROT
from unicorn import arm64_const as arm
from fex_alloc import PARAM, STUBS, NO_MEMORY, reg
from fex_memory import MemoryModel, MIB, PAGE, COMMIT


PREFIX = '_ZN3FEX7Windows12CallRetStack'
THREAD_TYPE = 'EPN7FEXCore4Core19InternalThreadStateE'
INIT = PREFIX + '16InitializeThread' + THREAD_TYPE
DESTROY = PREFIX + '13DestroyThread' + THREAD_TYPE
INFO = PREFIX + '13GetInfoThread' + THREAD_TYPE
RECOVER = PREFIX + '21HandleAccessViolation' + THREAD_TYPE + 'yRy'
THREAD, FRAME, RESULT = PARAM+0x2000, PARAM+0x3000, PARAM+0x4000
# Pinned ARM64 InternalThreadState / CPUState layout, checked via GetInfoThread
# and InitializeThread's published result, not inferred from allocation calls.
BASE_OFFSET, SP_OFFSET = 0x68, 0xb0
SIZE = 256*1024


class StackModel(MemoryModel):
    def __init__(self, dll, *, fail_commit=False):
        self.fail_commit = fail_commit
        super().__init__(dll)
        self.writeq(THREAD, FRAME)

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        if self.fail_commit and flags == COMMIT:
            return NO_MEMORY
        return super().allocate(base_pointer, size_pointer, flags, params, count)

    def info(self, thread=THREAD):
        self.vm.reg_write(reg(8), RESULT)
        self.call(INFO, thread)
        return struct.unpack('<3Q', self.vm.mem_read(RESULT, 24))

    def recover(self, address, thread=THREAD):
        self.writeq(RESULT, 0xdeadbeef)
        accepted = self.call(RECOVER, thread, address, RESULT)
        return accepted, self.readq(RESULT)


def check_lifecycle(dll, size):
    model = StackModel(dll)
    model.call(INIT, THREAD)
    assert not model.trapped
    base = model.readq(THREAD+BASE_OFFSET)
    start, end, default = model.info()
    assert (start, end, default) == (base-PAGE, base+size+PAGE, base+size//4)
    assert model.regions == {start: size+2*PAGE}
    assert model.readq(FRAME+SP_OFFSET) == default
    assert model.query(start)[6] == model.query(end-1)[6] == 0
    assert all(model.query(p)[6] == 4 for p in (base, base+size-PAGE))
    assert len(model.pages)*PAGE == size
    calls = [a for name, a in model.calls if name == 'NtAllocateVirtualMemory']
    assert [a[5] for a in calls] == [1, 4]  # NOACCESS reservation; READWRITE commit
    for address in (start, base-16, base, base+size-1, base+size, end-1):
        assert model.recover(address) == (1, default)
    for address in (0, start-1, end, 0xfffffff0):
        assert model.recover(address) == (0, 0xdeadbeef)
    model.call(DESTROY, THREAD)
    assert not model.regions and not model.pages
    return size


def check_guard_execution(dll):
    model = StackModel(dll)
    model.call(INIT, THREAD)
    start, end, default = model.info()
    code = STUBS+0xb000
    push = (0xa9bf0440, 0x91000400, 0xf1000463, 0x54ffffa1, 0xd65f03c0)
    # STP x0,x1,[x2,-16]!; ADD x0,x0,1; SUBS x3,x3,1; B.NE loop; RET
    pop = (0xa8c10440, 0xf1000463, 0x54ffffc1, 0xd65f03c0)
    # LDP x0,x1,[x2],16; SUBS x3,x3,1; B.NE loop; RET
    counts = {}
    for label, instructions, error in (('push', push, UC_ERR_WRITE_PROT),
                                       ('pop', pop, UC_ERR_READ_PROT)):
        model.vm.mem_write(code, struct.pack('<'+'I'*len(instructions), *instructions))
        model.vm.ctl_remove_cache(code, code+0x40)
        model.vm.reg_write(reg(0), 0x401000)
        model.vm.reg_write(reg(1), 0x12345678)
        model.vm.reg_write(reg(2), default)
        # Exercise repeated lower-guard hits and one upper-guard hit followed
        # by resumed accesses. Unicorn's read-protection TLB handling is not
        # a model of repeated Horizon upper-guard exception delivery.
        model.vm.reg_write(reg(3), 40000 if label == 'push' else 14000)
        model.vm.reg_write(reg(30), model.stop)
        pc, faults = code, 0
        while True:
            try:
                model.vm.emu_start(pc, model.stop, count=250000)
            except UcError as exc:
                assert exc.errno == error
                assert model.vm.reg_read(arm.UC_ARM64_REG_PC) == code
                # A failed pre/post-index pair must not publish its writeback.
                sp = model.vm.reg_read(reg(2))
                assert sp == (start+PAGE if label == 'push' else end-PAGE), (label, hex(sp), hex(start), hex(end), faults)
                address = sp-16 if label == 'push' else sp
                registers = [reg(i) for i in range(31)] + [arm.UC_ARM64_REG_SP, arm.UC_ARM64_REG_NZCV]
                context = [model.vm.reg_read(r) for r in registers]
                accepted, replacement = model.recover(address)
                assert accepted and replacement == default
                for r, value in zip(registers, context):
                    model.vm.reg_write(r, value)
                model.vm.reg_write(reg(2), replacement)
                pc = code
                faults += 1
                assert faults < 20
                continue
            assert model.vm.reg_read(arm.UC_ARM64_REG_PC) == model.stop
            assert model.vm.reg_read(reg(3)) == 0
            break
        assert faults == (9 if label == 'push' else 1)
        counts[label] = faults
    # A balanced pair still preserves guest/host return addresses after recovery.
    model.vm.mem_write(code+0x40, struct.pack('<3I', push[0], pop[0], 0xd65f03c0))
    model.vm.reg_write(reg(0), 0x41424344)
    model.vm.reg_write(reg(1), 0x123456789abcdef0)
    model.vm.reg_write(reg(2), default)
    model.vm.reg_write(reg(30), model.stop)
    model.vm.emu_start(code+0x40, model.stop, count=10)
    assert model.vm.reg_read(reg(0)) == 0x41424344
    assert model.vm.reg_read(reg(1)) == 0x123456789abcdef0
    assert model.vm.reg_read(reg(2)) == default
    model.call(DESTROY, THREAD)
    assert not model.regions
    return counts


def check_threads(dll, size):
    model = StackModel(dll)
    threads = []
    for i in range(34):
        thread, frame = PARAM+0x5000+i*0x200, PARAM+0xa000+i*0x100
        model.writeq(thread, frame)
        model.call(INIT, thread)
        assert not model.trapped
        threads.append(thread)
    assert len(model.regions) == 34
    reserved, committed = sum(model.regions.values()), len(model.pages)*PAGE
    assert reserved == 34*(size+2*PAGE) and committed == 34*size
    # Non-LIFO exits cover independent ownership rather than a global stack.
    for thread in threads[::2]+threads[1::2]:
        model.call(DESTROY, thread)
    assert not model.regions and not model.pages
    return {'threads': 34, 'reserved_bytes': reserved, 'committed_bytes': committed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check_lifecycle(args.before, 4*MIB)
    check_lifecycle(args.dll, SIZE)
    before, after = check_threads(args.before, 4*MIB), check_threads(args.dll, SIZE)
    faults = check_guard_execution(args.dll)
    for failure in ('reserve', 'commit'):
        model = StackModel(args.dll, fail_commit=failure == 'commit')
        model.fail_allocations = failure == 'reserve'
        model.call(INIT, THREAD)
        assert model.trapped
        assert model.readq(THREAD+BASE_OFFSET) == model.readq(FRAME+SP_OFFSET) == 0
        assert not model.regions and not model.pages
        assert any('STOP callret '+failure in line for line in model.logs)
    # The old initializer published a bogus stack after allocation failure.
    old = StackModel(args.before)
    old.fail_allocations = True
    old.call(INIT, THREAD)
    assert not old.trapped and old.readq(THREAD+BASE_OFFSET) == PAGE
    report = {
        'passed': True,
        'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
        'before': before, 'after': after,
        'saved_committed_bytes': before['committed_bytes']-after['committed_bytes'],
        'guard_recoveries': faults,
        'checks': [
            'Old/new linked initializers commit 4 MiB/256 KiB with both guards inaccessible',
            'Linked info/recovery obey inclusive start, exclusive end and leave unrelated faults unchanged',
            '40,000 ARM64 pushes / 14,000 pops hit lower/upper guards 9/1 times and resume after linked recovery',
            'Balanced pair preserves guest/host return values after overflow and underflow',
            '34 simultaneous prediction stacks free independently with no leaked reservations',
            'Reserve and commit failures stop before publication; failed commit releases reservation',
            'Old initializer reproduces invalid publication after OOM'],
        'scope': 'Linked ARM64 DLL + paired-access stress with modeled NT VM; hardware PES remains unverified.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
