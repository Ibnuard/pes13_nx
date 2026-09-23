"""Regression check using the actual old and corrected NRO packages."""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from nro_assets import inspect_nro

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('old', type=Path)
parser.add_argument('new', type=Path)
parser.add_argument('icon', type=Path)
parser.add_argument('--metadata-only', action='store_true', help='Also require identical executable sections')
args = parser.parse_args()
old = args.old.read_bytes()
new = args.new.read_bytes()
icon = args.icon.read_bytes()


def rejected(blob, message):
    try:
        inspect_nro(blob)
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('Invalid package was accepted')


rejected(old, 'Missing embedded icon')
info = inspect_nro(new, icon)
asset_start = struct.unpack_from('<I', new, 0x18)[0]
old_code_size = struct.unpack_from('<I', old, 0x18)[0]
if args.metadata_only:
    assert asset_start == old_code_size and new[:asset_start] == old[:old_code_size], 'Executable changed during icon packaging'

bad = bytearray(new)
struct.pack_into('<Q', bad, asset_start + 16, 0)
rejected(bad, 'Missing embedded icon')
bad = bytearray(new)
struct.pack_into('<Q', bad, asset_start + 8, len(new))
rejected(bad, 'asset range outside NRO')
bad = bytearray(new)
struct.pack_into('<Q', bad, asset_start + 32, 1)
rejected(bad, 'NACP must be exactly')
bad = bytearray(new)
icon_offset = struct.unpack_from('<Q', new, asset_start + 8)[0]
struct.pack_into('<Q', bad, asset_start + 24, icon_offset)
rejected(bad, 'Overlapping NRO assets')
bad = bytearray(new)
nacp_offset = struct.unpack_from('<Q', new, asset_start + 24)[0]
bad[asset_start + nacp_offset] = 0
rejected(bad, 'Unexpected NACP title')
print('PASS: old missing-icon package rejected; JPEG/NACP validated; damaged asset ranges rejected')
