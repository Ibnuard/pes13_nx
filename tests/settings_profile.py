"""Validate the checked-in production settings.dat independently."""
import hashlib
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
assert struct.unpack_from("<I", data, 0x18)[0] == 1
assert data == (root / "config/drive_c/PES13/settings.dat").read_bytes()
work = bytearray(data)
stored = struct.unpack_from("<H", work, 0x0c)[0]
struct.pack_into("<H", work, 0x0c, 0)
assert stored == crc16(work)
print(f"PES Documents profile: 1280x720, XInput enabled, checksum valid, SHA256={hashlib.sha256(data).hexdigest()}")
