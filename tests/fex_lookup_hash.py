"""Execute shipped folded-L1 lookup code and both real ARM64 emitter paths.

Synthetic collision workloads count actual dispatcher fallbacks, not FPS or
Switch elapsed time. NT locks, allocation and time are modeled by the shared
Unicorn harness; the cache methods, dispatcher constructor, indirect-branch
lowering method and their emitted instructions execute from the supplied DLL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import struct

import capstone
from unicorn import arm64_const as arm

from fex_alloc import PARAM, STACK, reg
from fex_dispatch_cache import CODE, HIT, Model
from fex_memory import MIB


class HashModel(Model):
    def listing(self, address, length):
        dis = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        return list(dis.disasm(bytes(self.vm.mem_read(address, length)), address))

    def emit_branch(self, guest_register):
        # Pinned Arm64JITCore layout, as exercised by fex_counter. These are
        # object inputs, not a replacement emitter or extracted instruction
        # sequence. The full linked Op_ExitFunction lowering runs below.
        emitter, mapping, ir = PARAM+0x5000, PARAM+0x6000, PARAM+0x7000
        self.vm.mem_write(emitter, bytes(0x400))
        self.vm.mem_write(ir, bytes(0x100))
        self.branch = CODE+0x8000
        self.writeq(emitter+0x48, self.branch)
        self.writeq(emitter+0x60+self.emitter_view_offset, mapping)
        self.writeq(emitter+0xd0+self.emitter_view_offset, self.ctx)
        self.vm.mem_write(mapping+3*4, struct.pack('<I', guest_register))
        # Physical GPR slot 3, high bit means a lowered register reference;
        # inline constant/entrypoint checks are executed and reject it.
        self.vm.mem_write(ir+4, struct.pack('<I', 0x80000043))
        self.call(self.method('15Op_ExitFunction'), emitter, ir, 0)
        assert not self.trapped
        end = self.readq(emitter+0x48)
        self.branch_register = guest_register
        self.branch_listing = self.listing(self.branch, end-self.branch)
        # Use the emitted instruction to find the actual dispatcher field.
        load = next(i for i in self.branch_listing if i.mnemonic == 'ldr'
                    and i.op_str.startswith('x1, [x28,'))
        offset = int(re.search(r'#(0x[0-9a-f]+)', load.op_str)[1], 16)
        self.writeq(self.frame+offset, self.loop)
        return hashlib.sha256(bytes(self.vm.mem_read(self.branch, end-self.branch))).hexdigest()

    def indirect(self, guest, flags=0xa0000000):
        self.writeq(self.frame+0x18, 0)
        for n in range(4, 31):
            self.vm.reg_write(reg(n), 0x56780000+n)
        self.vm.reg_write(reg(28), self.frame)
        self.vm.reg_write(reg(self.branch_register), guest)
        self.vm.reg_write(arm.UC_ARM64_REG_SP, STACK+0x3f000)
        self.vm.reg_write(arm.UC_ARM64_REG_NZCV, flags)
        before = [self.vm.reg_read(reg(n)) for n in range(4, 31)]
        destinations = self.destinations.copy()
        self.destinations[self.loop] = 'fallback'
        self.outcome, self.instructions, self.executing = None, 0, True
        try:
            self.vm.emu_start(self.branch, self.stop, count=2000)
        finally:
            self.executing = False
            self.destinations = destinations
        assert self.outcome in ('hit', 'fallback'), (self.outcome, self.trapped)
        assert self.vm.reg_read(arm.UC_ARM64_REG_NZCV) == flags
        assert [self.vm.reg_read(reg(n)) for n in range(4, 31)] == before
        assert self.vm.reg_read(arm.UC_ARM64_REG_SP) == STACK+0x3f000
        if self.outcome == 'fallback':
            assert self.readq(self.frame+0x18) == guest
        return self.outcome

    def l1_entry(self, guest):
        base = self.readq(self.obj+0x30)
        return base+self.l1_index(guest)*16


def assert_hash_instructions(model, listing, *, branch=False):
    eors = [i for i in listing if i.mnemonic == 'eor' and 'lsr #16' in i.op_str]
    if not model.fold_l1:
        assert not eors
        return
    assert len(eors) == 1, [(i.mnemonic, i.op_str) for i in listing]
    index = listing.index(eors[0])
    # Both paths use a non-flag-setting XOR and then a non-flag-setting AND;
    # full RIP remains available for the subsequent full-tag comparison.
    registers = re.fullmatch(r'(x\d+), (x\d+), (x\d+), lsr #16', eors[0].op_str)
    assert registers and registers[2] == registers[3]
    if branch:
        assert registers[2] == 'x'+str(model.branch_register)
    and_instruction = listing[index+1]
    assert and_instruction.mnemonic == 'and'
    assert and_instruction.op_str.endswith(', '+registers[1]+', lsl #4')


def collision_workload(dll, addresses, rounds=8):
    model = HashModel(dll)
    model.emit()
    for address in addresses:
        model.add(address, HIT)
    misses, hit_instructions, fallback_instructions = 0, 0, 0
    for _ in range(rounds):
        for address in addresses:
            result = model.dispatch(address)
            if result == 'fallback':
                misses += 1
                fallback_instructions += model.instructions
                assert model.find(address) == HIT
            else:
                assert result == 'hit'
                hit_instructions += model.instructions
    return {'accesses': rounds*len(addresses), 'dispatcher_fallbacks': misses,
            'hit_path_instructions': hit_instructions,
            'fallback_path_instructions_before_compileblock': fallback_instructions,
            'lookup_reserved_bytes': model.readq(model.obj+0x40)}


def exercise(dll):
    assert b'[FEX3-LOOKUP] v3' in dll.read_bytes()
    counts = {'dispatcher_checks': 0, 'indirect_checks': 0, 'cache_operations': 0,
              'dynamic_transitions': 0}
    emitted = []
    rng = random.Random(0xf3ca2026)
    for enabled in (False, True):
        model = HashModel(dll, dynamic=True, l2_enabled=enabled)
        emitted.append({'path': 'dispatcher', 'l2': enabled, 'sha256': model.emit()})
        assert model.readq(model.obj+0x38) == (8191 if enabled else 65535)
        assert_hash_instructions(model, model.listing(model.loop, 64))
        # Cross-page patterns hit different new indexes but exactly the same
        # old index. Tests also include high x86 DLL addresses and 64-bit tags.
        addresses = [0x00401000+i*0x10000 for i in range(32)]
        addresses += [0xfff19510, 0xffffffff, 0x100001234, 0xffffabcd00012345]
        addresses += [rng.randrange(0x10000, 0x100000000) for _ in range(64)]
        for guest_register in (9, 17, 24):
            emitted.append({'path': 'indirect', 'l2': enabled, 'register': guest_register,
                            'sha256': model.emit_branch(guest_register)})
            assert_hash_instructions(model, model.branch_listing, branch=True)
            for address in addresses:
                model.add(address, HIT)
                assert model.find(address) == HIT
                for flags in (0, 0x50000000, 0xa0000000, 0xf0000000):
                    assert model.dispatch(address, flags=flags) == 'hit'
                    assert model.instructions == 13
                    assert model.indirect(address, flags) == 'hit'
                    assert model.instructions == 9  # Includes target hook.
                    counts['dispatcher_checks'] += 1
                    counts['indirect_checks'] += 1
                # A different full tag at the same hash must miss the emitted
                # indirect probe; C++ lookup then restores the correct entry.
                collision = model.colliding_guest(address)
                assert model.l1_index(collision) == model.l1_index(address)
                model.add(collision, HIT)
                assert model.indirect(address) == 'fallback'
                assert model.find(address) == HIT
                assert model.indirect(address) == 'hit'
                counts['indirect_checks'] += 2
                counts['cache_operations'] += 3
        # Invalidation only clears its own full tag, even for same-index peers.
        first = 0x841020
        second = model.colliding_guest(first)
        model.add(first, HIT)
        model.add(second, HIT)
        entry = model.l1_entry(second)
        prior = bytes(model.vm.mem_read(entry, 16))
        model.invalidate(first, erase=True)
        assert bytes(model.vm.mem_read(entry, 16)) == prior
        assert model.find(first) == 0 and model.indirect(first) == 'fallback'
        assert model.find(second) == HIT and model.indirect(second) == 'hit'
        model.invalidate(second, erase=True)
        assert model.find(second) == 0 and model.indirect(second) == 'fallback'
        counts['cache_operations'] += 6
        # Dispatcher must not jump to zero when a stale tag has no host code.
        # The existing indirect branch contract does not synthesize null-host
        # entries; its semantics are intentionally not changed by this patch.
        null_guest = 0x762000
        model.vm.mem_write(model.l1_entry(null_guest), struct.pack('<QQ', 0, null_guest))
        assert model.dispatch(null_guest) == 'fallback'
        counts['dispatcher_checks'] += 1
        if enabled:
            update = model.method('20UpdateDynamicL1Stats')
            for hits, sizes in ((10000, (16384, 32768, 65536, 65536)),
                               (0, (32768, 16384, 8192, 8192))):
                for entries in sizes:
                    model.clock += 2_000_000
                    model.writeq(model.obj+0x68, hits)
                    model.call(update, model.obj, model.thread, second, HIT)
                    assert model.readq(model.obj+0x38) == entries-1
                    for address in addresses[:32]:
                        model.add(address, HIT)
                    for address in addresses[:32]:
                        assert model.find(address) == HIT
                        assert model.dispatch(address) == 'hit'
                        assert model.indirect(address) == 'hit'
                        counts['dispatcher_checks'] += 1
                        counts['indirect_checks'] += 1
                    counts['dynamic_transitions'] += 1
        # Model randomized replacements/erase/refill against an independent
        # full-address map, including collisions that can evict one another.
        pool = [0x12345000+i*0x10001 for i in range(32)]
        expected = {}
        for step in range(300):
            address = rng.choice(pool)
            operation = rng.randrange(4)
            if operation == 0 or address not in expected:
                if expected.get(address):
                    # Recompiled code is published only after invalidation;
                    # AddBlockMapping itself does not replace a populated L2.
                    model.invalidate(address, erase=True)
                host = HIT+(step % 16)*4
                model.add(address, host)
                expected[address] = host
            elif operation == 1:
                model.invalidate(address, erase=True)
                expected[address] = 0
            elif operation == 2:
                model.clear_l1_entry(address)
            else:
                model.invalidate(address)
            actual = model.find(address)
            assert actual == expected[address], (enabled, step, operation, hex(address),
                                                 hex(expected[address]), hex(actual))
            counts['cache_operations'] += 1
        model.call(model.method('22ClearThreadLocalCaches'), model.obj, 0)
        for address, host in expected.items():
            assert model.find(address) == host
            counts['cache_operations'] += 1
        if not enabled:
            assert sum(model.native_regions.values()) == MIB
            assert model.readq(model.obj+0x40) == MIB
    return counts, emitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Assertions required')
    assert b'[FEX3-LOOKUP] v2' in args.before.read_bytes()
    counts, emitted = exercise(args.dll)
    rng = random.Random(0x1616)
    patterns = {
        'same_offset_across_64k_regions': [0x401000+i*0x10000 for i in range(64)],
        'random_addresses': [rng.randrange(0x10000, 0xffff0000) for _ in range(128)],
        'single_hot_block': [0x401000],
        # Deliberately adverse to the new fold: exposes the tradeoff instead
        # of pretending every possible address pattern improves.
        'adverse_fold_collision_control': [0x401000 ^ (i*0x10001) for i in range(32)],
    }
    workloads = {name: {'before': collision_workload(args.before, addresses),
                        'after': collision_workload(args.dll, addresses)}
                 for name, addresses in patterns.items()}
    aligned = workloads['same_offset_across_64k_regions']
    assert aligned['before']['dispatcher_fallbacks'] == aligned['before']['accesses']
    assert aligned['after']['dispatcher_fallbacks'] == 0
    adverse = workloads['adverse_fold_collision_control']
    assert adverse['before']['dispatcher_fallbacks'] == 0
    assert adverse['after']['dispatcher_fallbacks'] == adverse['after']['accesses']
    for workload in workloads.values():
        assert workload['before']['lookup_reserved_bytes'] == MIB
        assert workload['after']['lookup_reserved_bytes'] == MIB
    report = {'passed': True, 'hardware_tested': False, 'checks': counts,
              'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'emitted_sha256': emitted, 'synthetic_workloads': workloads,
              'scope': 'Actual linked cache methods, dispatcher constructor and indirect-branch lowering, '
                       'executed emitted ARM64; host allocation, NT locks and time modeled. '
                       'Synthetic fallback counts do not predict PES FPS or on-device improvement.',
              'test_sources': {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                               for name in ('fex_lookup_hash.py', 'fex_dispatch_cache.py',
                                            'fex_lookup.py', 'fex_memory.py', 'fex_alloc.py')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
