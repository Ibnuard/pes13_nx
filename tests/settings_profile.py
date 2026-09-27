"""Validate the checked-in production settings.dat independently."""
import hashlib
import binascii
import struct
import importlib.util
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "tools/make-settings.py"
spec = importlib.util.spec_from_file_location("make_settings", module_path)
make_settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_settings)
SIZE, XINPUT = make_settings.SIZE, make_settings.XINPUT
crc16, validate = make_settings.crc16, make_settings.validate

root = Path(__file__).resolve().parents[1]
path = root / "config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat"
data = path.read_bytes()
validate(data)
assert len(data) == SIZE
assert struct.unpack_from("<II", data, 0x10) == (1280, 720)
assert struct.unpack_from("<H", data, 0x0e)[0] & XINPUT
assert struct.unpack_from("<H", data, 0x0e)[0] == make_settings.PRODUCTION_FLAGS
# Preserve the original display word. Its retail meaning is not verified;
# calling this field quality allowed the aspect candidate to change silently.
assert struct.unpack_from("<I", data, 0x18)[0] == 1, "Original display word 0x18 changed"
assert struct.unpack_from("<H", data, 0x0e)[0] == 0x0289
assert struct.unpack_from("<II", data, 0x1c) == (0, 1)
assert data == (root / "config/drive_c/PES13/settings.dat").read_bytes()
work = bytearray(data)
stored = struct.unpack_from("<H", work, 0x0c)[0]
struct.pack_into("<H", work, 0x0c, 0)
assert stored == crc16(work)
assert stored == (~binascii.crc_hqx(work, 0)) & 0xffff
print(f"PES Documents profile: 1280x720, display word 0x18=1, frame skipping off, XInput enabled, checksum valid, SHA256={hashlib.sha256(data).hexdigest()}")
