"""Package a hash-locked, reversible Wine x86 critical-section spin experiment.

Only the Wine DLL's conditional spin-entry branch changes to an unconditional
jump to its existing SpinCount==0 path. No PES executable or NRO is patched.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import zipfile

import pefile

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ntdll", type=Path, default=project /
                    "local/legacy-cleanup/wine/drive_c/windows/syswow64/ntdll.dll")
args = parser.parse_args()
original = args.ntdll.read_bytes()
expected_hash = "9ac8cd9fc36fa48c6c6a2f10876baa1300a6064b26cdfe9c5e8febcc1bd65c8a"
assert hashlib.sha256(original).hexdigest() == expected_hash, "Unrecognized x86 ntdll; refusing to patch"
pe = pefile.PE(data=original)
assert pe.FILE_HEADER.Machine == 0x14c
export = next(x for x in pe.DIRECTORY_ENTRY_EXPORT.symbols if x.name == b"RtlEnterCriticalSection")
assert export.address == 0x53170
assert pe.get_data(export.address, 15).hex() == "66905589e5568b7508837e14007450"
branch_rva = export.address + 13
branch_offset = pe.get_offset_from_rva(branch_rva)
assert original[branch_offset:branch_offset + 2] == b"\x74\x50"  # JE +0x50
target_rva = branch_rva + 2 + 0x50
assert target_rva == 0x531cf
assert pe.get_data(target_rva, 4) == b"\xf0\xff\x46\x04"  # LOCK INC [ESI+4]
patched = bytearray(original)
patched[branch_offset] = 0xeb  # JMP to the same existing no-spin entry
patched_pe = pefile.PE(data=bytes(patched))
checksum_offset = patched_pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum")
struct.pack_into("<I", patched, checksum_offset, patched_pe.generate_checksum())
patched = bytes(patched)
changed = [i for i, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]]
assert len(patched) == len(original)
assert branch_offset in changed
assert set(changed) <= {branch_offset, *range(checksum_offset, checksum_offset + 4)}
check = pefile.PE(data=patched)
assert check.OPTIONAL_HEADER.CheckSum == check.generate_checksum()
assert [(e.name, e.ordinal, e.address, e.forwarder) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols] == [
    (e.name, e.ordinal, e.address, e.forwarder) for e in check.DIRECTORY_ENTRY_EXPORT.symbols]
assert check.get_data(branch_rva, 2) == b"\xeb\x50"
assert pe.get_data(target_rva, 128) == check.get_data(target_rva, 128)

manifest = {
    "experiment": "PERF9 x86 critical-section no-spin",
    "runtime": "PERF8 unchanged",
    "original_sha256": expected_hash,
    "patched_sha256": hashlib.sha256(patched).hexdigest(),
    "function": "RtlEnterCriticalSection",
    "branch_rva": hex(branch_rva),
    "branch_file_offset": hex(branch_offset),
    "target_rva": hex(target_rva),
    "before": "74 50", "after": "eb 50",
    "other_changes": "PE checksum only",
    "exports_and_wait_path_unchanged": True,
    "hardware_tested": False,
}
config = (project / "config/drive_c/PES13/pes2013.wine-nx.txt").read_text()
assert "profile=0" in config and "verbose=0" in config
readme = (project / "docs/PERF9.md").read_text()
for name, dll in (("lock-test", patched), ("control", original)):
    archive = project / f"dist/pes13-perf9-{name}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("switch/pes13-nx/drive_c/windows/syswow64/ntdll.dll", dll)
        z.writestr("switch/pes13-nx/profile.txt", "0\n")
        z.writestr("switch/pes13-nx/drive_c/PES13/pes2013.wine-nx.txt", config)
        z.writestr("PERF9.md", readme)
        z.writestr("PERF9-manifest.json", json.dumps(dict(manifest, package=name), indent=2) + "\n")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read("switch/pes13-nx/drive_c/windows/syswow64/ntdll.dll") == dll
    print(f"{archive}\nSHA256 {hashlib.sha256(archive.read_bytes()).hexdigest()}")
print(json.dumps(manifest, indent=2))
