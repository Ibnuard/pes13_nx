"""Validate NRO metadata needed by Sphaira's forwarder installer."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

NRO_RELATIVE = 'switch/pes13-nx/pes13-nx.nro'
PACKAGE_VERSION = '0.2.0'


def jpeg_dimensions(data):
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('Icon must be a complete JPEG image')
    offset = 2
    while offset < len(data):
        if data[offset] != 0xff:
            raise ValueError('Invalid JPEG marker')
        while offset < len(data) and data[offset] == 0xff:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in (0xda, 0xd9):
            break
        if offset + 2 > len(data):
            break
        size = struct.unpack_from('>H', data, offset)[0]
        if size < 2 or offset + size > len(data):
            raise ValueError('Truncated JPEG segment')
        if marker in (0xc0, 0xc1, 0xc2):
            if marker != 0xc0 or size < 8:
                raise ValueError('Icon must use baseline JPEG encoding')
            precision, height, width, components = struct.unpack_from('>BHHB', data, offset + 2)
            if precision != 8 or components != 3 or size != 8 + components * 3:
                raise ValueError('Icon must use 8-bit, three-component JPEG encoding')
            return width, height
        offset += size
    raise ValueError('Missing JPEG frame header')


def inspect_nro(blob, expected_icon=None, *, expected_title='PES13-NX'):
    if len(blob) < 0x80 or blob[0x10:0x14] != b'NRO0':
        raise ValueError('Invalid NRO header')
    nro_size = struct.unpack_from('<I', blob, 0x18)[0]
    if nro_size < 0x80 or nro_size + 56 > len(blob):
        raise ValueError('Missing or truncated NRO asset header')
    magic, version, icon_off, icon_size, nacp_off, nacp_size, romfs_off, romfs_size = struct.unpack_from('<II6Q', blob, nro_size)
    if magic != int.from_bytes(b'ASET', 'little') or version != 0:
        raise ValueError('Invalid NRO asset header')
    if not icon_size:
        raise ValueError('Missing embedded icon: Sphaira rejects an empty icon with OwoBadArgs')
    if icon_size > 128 * 1024:
        raise ValueError('Icon exceeds the 128 KiB application icon budget')
    if nacp_size != 0x4000:
        raise ValueError('NACP must be exactly 0x4000 bytes')
    sections = []
    for name, offset, size in (('icon', icon_off, icon_size), ('nacp', nacp_off, nacp_size), ('romfs', romfs_off, romfs_size)):
        if not size:
            continue
        if offset < 56 or nro_size + offset + size > len(blob):
            raise ValueError(f'{name}: asset range outside NRO file')
        sections.append((offset, offset + size, name))
    sections.sort()
    if any(a[1] > b[0] for a, b in zip(sections, sections[1:])):
        raise ValueError('Overlapping NRO assets')
    icon = blob[nro_size + icon_off:nro_size + icon_off + icon_size]
    width, height = jpeg_dimensions(icon)
    if (width, height) != (256, 256):
        raise ValueError('Icon must be 256x256')
    if expected_icon is not None and icon != expected_icon:
        raise ValueError('Embedded icon differs from the project asset')
    nacp = blob[nro_size + nacp_off:nro_size + nacp_off + nacp_size]

    def string_at(offset, size):
        value = nacp[offset:offset + size]
        if b'\0' not in value:
            raise ValueError('Unterminated NACP string')
        return value.split(b'\0', 1)[0].decode('utf-8')

    title, author, display_version = string_at(0, 0x200), string_at(0x200, 0x100), string_at(0x3060, 16)
    if title != expected_title or not author or display_version != PACKAGE_VERSION:
        raise ValueError('Unexpected NACP title, author or package version')
    return {'nro_bytes': len(blob), 'executable_bytes': nro_size,
            'executable_sha256': hashlib.sha256(blob[:nro_size]).hexdigest(),
            'icon_bytes': icon_size, 'icon_width': width, 'icon_height': height,
            'icon_sha256': hashlib.sha256(icon).hexdigest(), 'nacp_bytes': nacp_size,
            'title': title, 'author': author, 'version': display_version}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nro', type=Path)
    parser.add_argument('--icon', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_nro(args.nro.read_bytes(), args.icon.read_bytes() if args.icon else None), indent=2))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
