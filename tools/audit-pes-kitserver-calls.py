"""Read-only execution of selected original x86 callsites, without DllMain.

Audits the exact supplied Kitserver files, not arbitrary plugin versions.
Scratch pointers model arguments; no game files are executed as host DLLs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, x86_const as x


INPUTS = {
    'kserv.dll': '06a6fea90a0c4eedba6e2b3d205052f2f273cb9a7427fd01b66416efb4a31123',
    'ballserv.dll': '04f811d7a7432db335c6317fac174f7234381bf86367deee753714dd9e892fef',
    'gameplayload.dll': '9e2a5b45c8f4f0eafca0aa5ae85db1aa81e0a380f6dea82cb90042aedc029028',
}


def model(raw):
    pe = pefile.PE(data=raw)
    base = pe.OPTIONAL_HEADER.ImageBase
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & -4096)
    vm.mem_write(base, pe.get_memory_mapped_image())
    vm.mem_map(0x30000000, 0x10000)  # scratch data
    vm.mem_map(0x31000000, 0x20000)  # x86 stack / local frame
    vm.reg_write(x.UC_X86_REG_ESP, 0x31001000)
    vm.reg_write(x.UC_X86_REG_EBP, 0x31010000)
    vm.reg_write(x.UC_X86_REG_EAX, 0x30001000)
    for reg in (x.UC_X86_REG_EBX, x.UC_X86_REG_EDI): vm.reg_write(reg, 0x30000000)
    vm.reg_write(x.UC_X86_REG_ESI, 0x30000800)
    vm.mem_write(0x30000000, struct.pack('<I', 0x30000800))
    return vm, pe


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    blobs = {name:(a.game/'kitserver13'/name).read_bytes() for name in INPUTS}
    for name, data in blobs.items(): assert hashlib.sha256(data).hexdigest() == INPUTS[name], name
    results = []
    for name, begin, call in (
        ('kserv.dll', 0x1000b2e8, 0x1000b300),
        ('kserv.dll', 0x1000b9a3, 0x1000b9b8),
        ('kserv.dll', 0x1000c073, 0x1000c088),
        ('ballserv.dll', 0x10004d98, 0x10004dac),
    ):
        vm, pe = model(blobs[name])
        imported = [e.address for d in pe.DIRECTORY_ENTRY_IMPORT if d.dll.lower() == b'zlib1.dll'
                    for e in d.imports if e.name == b'compress2']
        assert len(imported) == 1
        assert bytes(vm.mem_read(call, 6)) == b'\xff\x15' + struct.pack('<I', imported[0])
        if name == 'ballserv.dll': vm.reg_write(x.UC_X86_REG_EDI, 0x10000)
        vm.emu_start(begin, call, count=100)
        assert vm.reg_read(x.UC_X86_REG_EIP) == call
        args = struct.unpack('<5I', vm.mem_read(vm.reg_read(x.UC_X86_REG_ESP), 20))
        assert args[0] == 0x30001010 and args[2] == 0x30000800 and args[4] == 0
        results.append(dict(dll=name, call_va=hex(call), import_name='zlib1!compress2',
                            source_bytes=args[3], level=args[4]))
    vm, pe = model(blobs['gameplayload.dll'])
    vm.reg_write(x.UC_X86_REG_EAX, 0)  # original LoadLibraryW returned failure
    vm.emu_start(0x100013dd, 0x100013f0, count=5)
    assert vm.reg_read(x.UC_X86_REG_EIP) == 0x100013f0
    report = dict(passed=True, hardware_tested=False, input_sha256=INPUTS,
        compression_calls=results,
        optional_parent_load_failure='Original x86 test/jz path reaches 0x100013f0, continuing module setup.',
        no_input_modified=True,
        conclusion='Inspected kit/font/number/ball calls already use compress2 level 0; do not ship a slower level-1 zlib patch.',
        limits='This executes callsite argument setup and the optional-load failure branch only, not a whole plugin or match.')
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
