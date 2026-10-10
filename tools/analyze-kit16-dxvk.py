"""Correlate the Kit16 device failure with the exact shipped DXVK instruction."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import capstone
import pefile

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('log', 'dll', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    s = a.log.read_text(errors='replace')
    assert sha(a.dll) == '265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa'
    assert '[FEX3-SCRATCH] v2 kit16' in s
    base = int(re.search(r'attach name=d3d9.dll status=00000000 base=([0-9A-Fa-f]+)', s)[1], 16)
    faults = [dict(seconds=float(t), address=int(addr, 16), pc=int(pc, 16), tid=int(tid, 16))
        for t, addr, pc, tid in re.findall(
            r'\[([\d.]+)\] wine: Unhandled page fault on read access to ([\dA-Fa-f]+) at address ([\dA-Fa-f]+) \(thread ([\dA-Fa-f]+)\)', s)]
    assert faults and faults[0]['address'] == 0x6c
    rva = faults[0]['pc'] - base
    assert rva == 0x18fa4f
    pe = pefile.PE(str(a.dll))
    assert pe.FILE_HEADER.Machine == 0x14c
    code = pe.get_data(rva - 13, 32)
    assert code.startswith(bytes.fromhex('8b462ca80275208b96b00000008b4a6c'))
    instructions = [dict(rva=hex(i.address), instruction=i.mnemonic + ' ' + i.op_str)
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, rva - 13)]
    allocs = [dict(seconds=float(t), bytes=int(size), memory_type=int(typ), result=int(rc))
        for t, size, typ, rc in re.findall(
            r'\[([\d.]+)\] \[NXVK\] vkAllocateMemory of (\d+) bytes of memory type (\d+) failed: (-?\d+)', s)]
    assert len(allocs) == 32
    assert '[EXIT] NtTerminateProcess(self) exit_code=0xc0000005' in s
    assert 'STOP compiler scratch failed' not in s
    report = dict(passed=True, input_sha256=sha(a.log), input_bytes=a.log.stat().st_size,
        dll_sha256=sha(a.dll), module_base=hex(base), first_fault_rva=hex(rva),
        faults=faults, fault_instructions=instructions, vulkan_allocation_failures=allocs,
        failure_sizes=dict(collections.Counter(x['bytes'] for x in allocs)),
        scratch_stop_present=False, self_terminated=True,
        interpretation='DXVK storage pointer is NULL at the faulting read. The surrounding instructions and pinned source match DxvkImage::assignStorageWithUsage after failed initial storage allocation.',
        limits='Allocation logging is bounded; 32 entries are not the total failure count. Earlier Vulkan failures may recover. The source-function attribution is an inference from disassembly, not original release debug symbols. This does not measure total free memory or prove every freeze has the same cause.',
        sources={'tools/analyze-kit16-dxvk.py': sha(Path(__file__))})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'module_base', 'first_fault_rva', 'faults', 'failure_sizes', 'self_terminated')}))


if __name__ == '__main__':
    main()
