"""Validate and package only the separate developer diagnostic NRO and guide."""
from pathlib import Path
import hashlib
import json
import struct
import zipfile

project = Path(__file__).resolve().parents[1]
relative = 'switch/pes13-nx/pes13-settings-debug.nro'
nro = project / 'dist/settings-debug' / relative
data = nro.read_bytes()
assert data[16:20] == b'NRO0'
assert b'pes13-settings-debug-0.2.0' in data
assert b'/PES13/settings.exe' in data
assert b'/pes13-settings-debug.log' in data
assert b'[PES13-SETTINGS-FILE]' in data
size = struct.unpack_from('<I', data, 0x18)[0]
magic, version, icon_offset, icon_size, nacp_offset, nacp_size, _, _ = struct.unpack_from('<II6Q', data, size)
assert magic == int.from_bytes(b'ASET', 'little') and version == 0
assert data[size + icon_offset:size + icon_offset + icon_size] == (project / 'assets/icon.jpg').read_bytes()
assert nacp_size == 0x4000 and size + nacp_offset + nacp_size <= len(data)
nacp = data[size + nacp_offset:size + nacp_offset + nacp_size]
assert nacp[:512].split(b'\0')[0] == b'PES13 Settings Debug'
assert nacp[0x3060:0x3070].split(b'\0')[0] == b'0.2.0'
production = project / 'dist/sd/switch/pes13-nx/pes13-nx.nro'
assert hashlib.sha256(production.read_bytes()).hexdigest() == '4bb75282b801eefea79a42a00a09cfdeb150d55d5d04440f0d90f333e7a32e16'
archive = project / 'dist/pes13-settings-debug.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
    output.write(nro, relative)
    output.write(project / 'docs/SETTINGS-DEBUG.md', 'SETTINGS-DEBUG.md')
    for path in sorted((project / 'dist/settings-debug/switch/pes13-nx/drive_c').rglob('*')):
        if path.is_file():
            relative_data = path.relative_to(project / 'dist/settings-debug').as_posix()
            assert path.name in ('riched20.dll', 'usp10.dll', 'msls31.dll', 'settings.dat')
            output.write(path, relative_data)
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    assert sum(name.endswith('.nro') for name in output.namelist()) == 1
report = {'nro_sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
          'zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
          'production_nro_unchanged': True, 'game_executable_included': False,
          'hardware_tested': False}
archive.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
