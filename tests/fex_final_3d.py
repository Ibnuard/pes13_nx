"""Execute final FEX policy and CRC emitter against mutations and page ends.

Runs delivered ARM64 DLL instructions. It does not model full PES execution,
Horizon scheduling or GPU time and cannot establish a device FPS result.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import zlib

from fex_alloc import Model, PARAM, reg
from fex_code_growth import CodeModel
from fex_memory import MIB
from unicorn import arm64_const as arm


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policy(dll):
    m = Model(dll)
    image, name = 0x31000000, PARAM + 0x2000
    m.vm.mem_map(image, 0x10000)
    header = bytearray(4096)
    struct.pack_into('<H', header, 0, 0x5a4d)
    struct.pack_into('<I', header, 0x3c, 0x80)
    struct.pack_into('<IHH', header, 0x80, 0x4550, 0x14c, 2)
    struct.pack_into('<H', header, 0x94, 0xe0)
    table = 0x178
    for offset, n, rva, length, flags in ((table, b'.text', 0x1000, 0x7000, 0x60000020),
                                        (table+40, b'.data', 0x8000, 0x1000, 0xc0000040)):
        header[offset:offset+8] = n.ljust(8, b'\0')
        struct.pack_into('<II', header, offset+8, length, rva)
        struct.pack_into('<I', header, offset+36, flags)
    m.vm.mem_write(image, bytes(header))
    checks = 0

    def check(expected, path='C:\\PES13\\pes2013.exe', address=image+0x1234, size=100,
              base=image, image_size=0x10000):
        nonlocal checks
        m.vm.mem_write(name, path.encode()+b'\0')
        value = m.call('PES13FexCanBatchSMC', base, image_size, name, address, size)
        assert value == expected and not m.trapped, (path, address, size, value)
        checks += 1

    for path in ('pes2013.exe', 'C:\\PES13\\PES2013.EXE', 'c:/dxvk/d3d9.dll'):
        check(1, path)
    for path in ('rld.dll', 'd3d9.dll.old', 'badpes2013.exe', 'foo.dll', ''):
        check(0, path)
    for addr, length in ((image, 16), (image+0x8000, 10), (image+0x7fff, 2),
                         (image+0x1234, 0), (image+0x1234, 65537), (image-1, 8),
                         (image+0xfffe, 10), ((1 << 64)-4, 10)):
        check(0, address=addr, size=length)
    check(1, address=image+0x7fff, size=1)
    for flags in (0xe0000020, 0x20000020, 0x40000020, 0):
        m.vm.mem_write(image+table+36, struct.pack('<I', flags))
        check(0)
    m.vm.mem_write(image, bytes(header))
    for offset, fmt, value in ((0x3c, '<I', 0xfffffff0), (0x84, '<H', 0xaa64),
                               (0x86, '<H', 97), (0x94, '<H', 0xffff),
                               (table+8, '<I', 0xffffffff)):
        m.vm.mem_write(image+offset, struct.pack(fmt, value))
        check(0)
        m.vm.mem_write(image, bytes(header))
    return checks


def emit_tests(dll):
    m = Model(dll)
    method = next(name for name in m.symbols if '15Op_ValidateCode' in name)
    emitter, mapping, node, ir, buffer = (PARAM+o for o in (0x3000, 0x3400, 0x3600, 0x3800, 0x4000))
    guest = 0x31000000
    m.vm.mem_map(guest, 0x10000)  # Following page intentionally absent.
    code_sizes, mutations = {}, 0
    for length in (*range(1, 16), 16, 31, 32, 63, 64, 124, 127, 128, 254, 255):
        m.vm.mem_write(emitter, bytes(0x400))
        m.writeq(emitter+0x48, buffer)
        m.writeq(emitter+0x60, mapping)
        for slot, register in ((3, 9), (4, 10), (5, 11)):
            m.vm.mem_write(mapping+slot*4, struct.pack('<I', register))
        m.vm.mem_write(node+0x10, b'\x43')
        m.vm.mem_write(ir, struct.pack('<IIIB', 0, 0x80000044, 0x80000045, length))
        m.call(method, emitter, ir, node)
        assert not m.trapped
        end = m.readq(emitter+0x48)
        m.vm.mem_write(end, struct.pack('<I', 0xd65f03c0))
        m.vm.ctl_remove_cache(buffer, end+4)
        m.symbols['guard'] = buffer
        code_sizes[length] = (end-buffer)//4
        original = bytes((i*37+11) & 255 for i in range(length))
        expected = zlib.crc32(original, 0xffffffff) ^ 0xffffffff
        address = guest + 0x10000 - length

        def run(data):
            m.vm.mem_write(address, data)
            m.vm.reg_write(reg(10), expected)
            m.vm.reg_write(reg(11), address)
            m.call('guard')
            assert not m.trapped
            assert m.vm.reg_read(reg(10)) == expected and m.vm.reg_read(reg(11)) == address
            return m.vm.reg_read(reg(9))

        assert run(original) == 0
        for byte in range(length):
            changed = bytearray(original)
            changed[byte] ^= 1 << (byte % 8)
            assert run(bytes(changed)) == 1
            mutations += 1
        assert run(original) == 0
    # Only emitted CRC helper bodies, not complete FEX blocks or FPS. Whole
    # block lowering additionally removes intermediate control-flow/state gaps.
    return {'mutations': mutations, 'crc_arm_instructions': code_sizes,
            'example_128_bytes': {'old_32_four_byte_checks': 32*code_sizes[4],
                                 'new_first4_plus_remaining124': code_sizes[4]+code_sizes[124]}}


class TrackerModel(Model):
    invalidations = 0

    def hook(self, vm, pc, size, user):
        if hasattr(self, 'invalidate') and pc == self.invalidate:
            self.invalidations += 1
            self.host_return()
            return
        if self.hooks.get(pc) in ('RtlAcquireSRWLockExclusive', 'RtlReleaseSRWLockExclusive',
                                  'RtlAcquireSRWLockShared', 'RtlReleaseSRWLockShared',
                                  'RtlWakeAllConditionVariable'):
            self.host_return()
            return
        super().hook(vm, pc, size, user)


def tracker_test(dll):
    m = TrackerModel(dll)
    def symbol(s):
        return next(n for n in m.symbols if s in n)
    m.invalidate = m.symbols[symbol('26InvalidateIntervalInternalE')]
    change = symbol('34HandleMemoryProtectionNotificationE')
    query = symbol('20QueryExecutableRangeE')
    obj, result = PARAM+0x7000, PARAM+0x7800
    m.vm.mem_write(obj, bytes(256))  # Empty tracker; context invalidation mocked.

    def notify(base, size, prot):
        m.call(change, obj, base, size, prot)
        assert not m.trapped

    def writable(address):
        m.vm.reg_write(reg(8), result)
        m.call(query, obj, address)
        assert not m.trapped
        start, length, write = struct.unpack('<QQB', m.vm.mem_read(result, 17))
        assert start <= address < start+length
        return bool(write)

    notify(0x400000, 0x4000, 0x40)  # RWX
    assert writable(0x400000)
    notify(0x401000, 0x1000, 0x20)  # Restore only middle page to RX.
    cleared = not writable(0x401000)
    assert writable(0x400000) and writable(0x402000)
    notify(0x401000, 0x1000, 0x40)
    assert writable(0x401000)
    notify(0x400000, 0x4000, 0x20)
    cleared_all = not writable(0x403000)
    assert m.invalidations == 4
    return {'partial_rx_cleared': cleared, 'whole_rx_cleared': cleared_all, 'invalidations': m.invalidations}


def spare_test(dll):
    m = CodeModel(dll)
    m.profile = 2
    first = m.backend()
    original = m.readq(first+16)
    original_rx = m.check_code(original, 128*MIB)
    assert m.code_requests == [128*MIB, 128*MIB] and len(m.code) == 2
    m.call('PES13FexPrimeCodeCache', 128*MIB)
    assert len(m.code_requests) == 2, 'priming must only happen once'
    # Simulate the exact late VA fragmentation observed on Switch.
    m.maximum = 8*MIB
    m.signal(first, True)  # A live signal reference must keep the old generation.
    m.grow(first)
    current = m.readq(first+16)
    current_rx = m.check_code(current, 128*MIB)
    assert current_rx != original_rx and original_rx in m.code
    assert len(m.code_requests) == 2 and not m.released, 'spare must avoid any fresh VM request'
    m.signal(first, False)
    m.cleanup()
    assert len(m.released) == 2
    # Optional reserve failure is not a startup failure or repeated attempt.
    m = CodeModel(dll, maximum=8*MIB)
    m.profile = 2
    first = m.backend()
    m.check_code(m.readq(first+16), 8*MIB)
    requests = list(m.code_requests)
    assert requests == [128*MIB, 64*MIB, 32*MIB, 16*MIB, 8*MIB, 128*MIB]
    m.call('PES13FexPrimeCodeCache', 128*MIB)
    assert m.code_requests == requests
    m.cleanup()
    return ['128 MiB rollover succeeds with late allocation cap 8 MiB and zero new mapping calls',
            'old generation stays alive until its signal/backend references release it',
            'optional spare failure falls back normally, without repeated startup attempts']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dll', type=Path)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    old = tracker_test(args.before)
    new = tracker_test(args.dll)
    assert not old['partial_rx_cleared'] and not old['whole_rx_cleared'], old
    assert new['partial_rx_cleared'] and new['whole_rx_cleared'], new
    report = {'passed': True, 'dll_sha256': sha(args.dll), 'before_sha256': sha(args.before),
              'scope_policy_cases': policy(args.dll), 'guard': emit_tests(args.dll),
              'old_tracker': old, 'new_tracker': new, 'spare': spare_test(args.dll), 'hardware_tested': False,
              'scope': 'Linked ARM64 policy, interval tracker, CRC emitter; mocked NT locks/invalidation'}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
