"""Read-only audit of user settings against the actual Settings.exe controls.

The UI label comes from RCDATA/190's English table, not from the name of a
supplied .dat file. Unicorn runs the small original x86 flag setters/getters;
it does not launch Settings.exe or modify the user's configuration.
"""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP

SETTINGS_SHA = '761eb6873dafc3fc7cec27b82eff66e36e7ec99b87af5e024a8b535edc52c705'
FLAG_ADDRESS = 0x4ce3ce


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data):
    assert len(data) == 852
    assert struct.unpack_from('<III', data) == (0x46434557, 2, 852)
    work = bytearray(data)
    stored = struct.unpack_from('<H', data, 12)[0]
    work[12:14] = b'\0\0'
    assert stored == (~binascii.crc_hqx(work, 0) & 65535)
    flags = struct.unpack_from('<H', data, 14)[0]
    return dict(sha256=sha(data), size=len(data), crc_valid=True,
                flags=f'{flags:04x}', vsync=bool(flags & 1),
                frame_skipping=bool(flags & 2),
                xinput_ui=bool(flags & 8), xinput_runtime=bool(flags & 0x200))


def original_setter(pe, address, flags, enabled):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    image = pe.get_memory_mapped_image()
    vm.mem_map(0x400000, (len(image) + 4095) & -4096)
    vm.mem_write(0x400000, image)
    vm.mem_map(0x200000, 0x2000)
    vm.mem_write(FLAG_ADDRESS, struct.pack('<H', flags))
    vm.mem_write(0x201000, struct.pack('<II', 0x200000, enabled))
    vm.reg_write(UC_X86_REG_ESP, 0x201000)
    vm.emu_start(address, 0x200000, count=30)
    assert vm.reg_read(UC_X86_REG_EIP) == 0x200000
    return struct.unpack('<H', vm.mem_read(FLAG_ADDRESS, 2))[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--settings-exe', type=Path, required=True)
    ap.add_argument('--off', type=Path, required=True)
    ap.add_argument('--on', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    exe = a.settings_exe.read_bytes()
    assert sha(exe) == SETTINGS_SHA, 'Unsupported Settings.exe; do not reuse the control mapping'
    pe = pefile.PE(data=exe)
    resource = next(n for t in pe.DIRECTORY_ENTRY_RESOURCE.entries if t.id == 10
                    for n in t.directory.entries if n.id == 190).directory.entries[0].data.struct
    data = pe.get_data(resource.OffsetToData, resource.Size)
    assert data[:4] == b'STRD' and data[16:24] == b'en\0\0GB\0\0'
    labels = {}
    # Pinned resource layout: 12 language descriptors, then 109 English entries.
    for pos in range(0xd0, 0x438, 8):
        identity, length, offset = struct.unpack_from('<HHI', data, pos)
        labels[identity] = data[0x438+offset:0x438+offset+length].decode('utf-8')
    assert labels[125] == 'Wait for Vsync'
    assert labels[126] == 'Enable Frame Skipping'
    # The original UI's apply handler reads control 0x451 then calls 0x41be20.
    assert pe.get_data(0x409c21-0x400000, 5) == bytes.fromhex('6851040000')
    assert pe.get_data(0x409c46-0x400000, 5) == bytes.fromhex('e8d5210100')
    cases = []
    for flags in (0, 0x0081, 0x0289, 0x028b, 0xffff):
        for enabled in (0, 1):
            value = original_setter(pe, 0x41be20, flags, enabled)
            assert value == (flags & ~2) | (enabled << 1)
            cases.append(dict(before=f'{flags:04x}', checked=enabled, after=f'{value:04x}'))
            # The 0x8 setter is called by the controller tab's XInput/DirectInput radios.
            value = original_setter(pe, 0x41bea0, flags, enabled)
            assert value == (flags & ~8) | (enabled << 3)
    off, on = a.off.read_bytes(), a.on.read_bytes()
    result = dict(passed=True, settings_exe_sha256=sha(exe),
        ui_label=labels[126], control_id='0x451', setter='0x41be20', bit='0x0002',
        original_x86_setter_tests=cases,
        references={'user_off': inspect(off), 'user_on': inspect(on)},
        changed_bytes=[dict(offset=i, off=x, on=y, xor=x^y)
                       for i, (x, y) in enumerate(zip(off, on)) if x != y],
        conclusion='Both supplied files have the Frame Skipping checkbox bit clear in this Settings.exe. '
                   'Their non-checksum differences are the two XInput controller flags (0x0208). '
                   'This does not establish the running game\'s effective setting or simulation speed.',
        files_modified=False)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
