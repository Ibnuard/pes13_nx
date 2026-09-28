"""Create the fixed PES 2013 settings.dat used by the Switch production profile."""
import argparse
import hashlib
import struct
from pathlib import Path

SIZE = 0x354
MAGIC = 0x46434557
VERSION = 2
XINPUT = 0x200
# PRODUCTION_FLAGS: 0x0289 (VSync enabled, Frame Skipping disabled, XInput enabled)
PRODUCTION_FLAGS = 0x0289
SUPPORTED_SETTINGS_SHA256 = "761eb6873dafc3fc7cec27b82eff66e36e7ec99b87af5e024a8b535edc52c705"


def crc16(data):
    value = 0
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ 0x1021) & 0xffff if value & 0x8000 else (value << 1) & 0xffff
    return (~value) & 0xffff


def validate(data):
    if len(data) != SIZE:
        raise ValueError(f"settings.dat must be {SIZE} bytes")
    if struct.unpack_from("<III", data) != (MAGIC, VERSION, SIZE):
        raise ValueError("Unexpected PES settings header")
    stored = struct.unpack_from("<H", data, 0x0c)[0]
    work = bytearray(data)
    struct.pack_into("<H", work, 0x0c, 0)
    if stored != crc16(work):
        raise ValueError("Invalid PES settings checksum")
    if not struct.unpack_from("<H", data, 0x0e)[0] & XINPUT:
        raise ValueError("PES XInput flag is not enabled")


def main():
    import pefile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("settings_exe", type=Path, help="The user's original PES 2013 settings.exe")
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    source = args.settings_exe.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != SUPPORTED_SETTINGS_SHA256:
        raise ValueError(f"Unsupported settings.exe SHA256: {digest}")
    pe = pefile.PE(data=source)
    if pe.FILE_HEADER.Machine != 0x14c or pe.OPTIONAL_HEADER.ImageBase != 0x400000:
        raise ValueError("settings.exe is not the supported PE32 image")
    read = lambda va, size: pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, size)

    data = bytearray(SIZE)
    struct.pack_into("<III", data, 0, MAGIC, VERSION, SIZE)
    # User-tested Settings.exe preset: XInput plus the matching display flags.
    struct.pack_into("<H", data, 0x0e, PRODUCTION_FLAGS)
    struct.pack_into("<II", data, 0x10, args.width, args.height)
    # Preserve the user-tested display words. Retail field semantics are not
    # verified; 0x18 is an aspect candidate, not a proven quality setting.
    struct.pack_into("<I", data, 0x18, 1)
    struct.pack_into("<I", data, 0x1c, 0)
    struct.pack_into("<I", data, 0x20, 1)
    struct.pack_into("<I", data, 0x28, 0x166b)
    struct.pack_into("<I", data, 0x4c, 0x1000)
    data[0x124:0x134] = read(0x47a660, 0x10)
    data[0x134:0x194] = read(0x495500, 0x60)
    direct_input_defaults = read(0x4954a0, 0x60)
    for controller in range(1, 5):
        offset = 0x134 + controller * 0x70
        data[offset:offset + 0x60] = direct_input_defaults
    struct.pack_into("<H", data, 0x0c, crc16(data))
    validate(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"{args.output}: {len(data)} bytes SHA256={hashlib.sha256(data).hexdigest()} XInput=1")


if __name__ == "__main__":
    main()
