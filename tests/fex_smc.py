"""Execute the linked FEX code-validation emitter and its emitted ARM64 code.

Exercises the checks newly enabled for writable guest blocks, with writable
guest memory and no write faults. This does not emulate the full FEX dispatcher,
Wine, concurrent Switch CPUs, or Horizon page permissions.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import subprocess
import zlib

from fex_alloc import Model, PARAM, reg


def check_ranges(project, output):
    source = project / 'tests/fex_smc_ranges.cpp'
    policy = project / 'src/fex/horizon_smc.h'
    policy_sha = hashlib.sha256(policy.read_bytes()).hexdigest()
    prefix = ['wsl', '-d', 'Ubuntu', '-u', 'blekjek', '--exec'] if os.name == 'nt' else []

    def path(p):
        return (subprocess.check_output(prefix+['wslpath', '-a', '-u', str(p)], text=True).strip()
                if prefix else str(p))

    output.parent.mkdir(parents=True, exist_ok=True)
    executable = output.parent / 'range-test'
    subprocess.run(prefix+['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', path(source), '-o', path(executable)], check=True)
    report = json.loads(subprocess.check_output(prefix+[path(executable)], text=True))
    assert report['passed'] and report['checks'] >= 3000
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == policy_sha
    report['policy_sha256'] = policy_sha
    (output.parent / 'range-tests.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    ranges = check_ranges(project, args.output.resolve())
    model = Model(args.dll)
    method = next(name for name in model.symbols if '15Op_ValidateCode' in name)
    # Layouts from the pinned FEX source: emitter CurrentOffset +0x48,
    # GeneralRegisters +0x60; OrderedNode.Reg +0x10. IROp_ValidateCode has
    # a four-byte header, two immediate register wrappers, then CodeLength.
    emitter, mapping, node, ir, buffer = (PARAM+offset for offset in (0x3000, 0x3400, 0x3600, 0x3800, 0x4000))
    guest = 0x31000000
    model.vm.mem_map(guest, 4096)  # The following page deliberately unmapped.
    cases = 0
    for destination, crc_reg, base_reg in ((9, 10, 11), (17, 12, 13), (24, 14, 15)):
        for length in range(1, 16):  # Every legal x86 instruction length.
            model.vm.mem_write(emitter, bytes(0x400))
            model.writeq(emitter+0x48, buffer)
            model.writeq(emitter+0x60+model.emitter_view_offset, mapping)
            for slot, register in ((3, destination), (4, crc_reg), (5, base_reg)):
                model.vm.mem_write(mapping+slot*4, struct.pack('<I', register))
            model.vm.mem_write(node+0x10, b'\x43')
            model.vm.mem_write(ir, struct.pack('<IIIB', 0, 0x80000044, 0x80000045, length))
            model.call(method, emitter, ir, node)
            assert not model.trapped
            end = model.readq(emitter+0x48)
            assert buffer < end < buffer+512
            model.vm.mem_write(end, struct.pack('<I', 0xd65f03c0))  # RET
            model.vm.ctl_remove_cache(buffer, end+4)
            model.symbols['guard'] = buffer
            address = guest+4096-length
            original = (b'\xb8\x2a\x00\x00\x00' if length == 5 else
                        bytes((0x31+i*17) & 255 for i in range(length)))
            crc = zlib.crc32(original, 0xffffffff) ^ 0xffffffff

            def execute(data):
                model.vm.mem_write(address, data)
                model.vm.reg_write(reg(crc_reg), crc)
                model.vm.reg_write(reg(base_reg), address)
                model.call('guard')
                assert not model.trapped
                assert model.vm.reg_read(reg(base_reg)) == address
                assert model.vm.reg_read(reg(crc_reg)) == crc
                return model.vm.reg_read(reg(destination))

            assert execute(original) == 0
            if length == 5:
                assert execute(b'\xb8\x00\x10\x00\x00') == 1
                assert execute(original) == 0
            # Checks must detect opcode/immediate/displacement changes, even
            # with no host protection fault and without FlushInstructionCache.
            for byte in range(length):
                for bit in range(8):
                    changed = bytearray(original)
                    changed[byte] ^= 1 << bit
                    assert execute(bytes(changed)) == 1, (length, byte, bit)
                    cases += 1
            assert execute(original) == 0

    # The reported failure's exact shape: MOV EAX, imm32; RET. The unchanged
    # guard accepts 42, the updated immediate (4096) must take invalidation.
    # Generic tests above also cover each of the five instruction bytes.
    assert cases == 2880
    model.logs.clear()
    for i in range(20):
        model.call('PES13FexLogSMCProtectFailure', 0x12340000+i, 4096, 0x20, 0xc000000d)
        assert not model.trapped, f'protection logger trapped on call {i}'
    assert len(model.logs) == 8 and all('[FEX3-SMC] protection failed' in line for line in model.logs), model.logs
    assert '0000000012340000' in model.logs[0] and '00000000c000000d' in model.logs[0]
    report = {
        'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        'policy_sha256': hashlib.sha256((project / 'src/fex/horizon_smc.h').read_bytes()).hexdigest(),
        'range_selection': ranges, 'emitted_guard_mutations_detected': cases,
        'checks': ['actual linked emitter, three register assignments, x86 lengths 1..15',
                   'unchanged code accepted; every single-bit mutation detected without write faults',
                   'exact-length reads at an unmapped page boundary', 'protection error logging limited to eight reports'],
        'scope': 'ARM64 instruction model and permission policy, not full FEX/Wine/Horizon execution',
        'on_device_tested': False,
    }
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
