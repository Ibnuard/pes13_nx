"""Build reproducible DXVK D3D9 A/B overlays for the PERF34 profile.

The PES13 executable is 32-bit, so only the x32 d3d9.dll from each upstream
archive is installed.  The verified PERF34 NRO, Box64 preset, configuration
and game files are copied byte-for-byte from the existing PERF34 CONFIG ZIP.
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "dist/pes13-perf34-config.zip"
SOURCE = PROJECT / "local/dxvk-ab/source"
PREFIX = "switch/pes13-nx/"
DLL_PATH = PREFIX + "drive_c/PES13/d3d9.dll"
DXVK_DLL_PATH = PREFIX + "drive_c/dxvk/d3d9.dll"
DLL_PATHS = (DLL_PATH, DXVK_DLL_PATH)
NRO_PATH = PREFIX + "pes13-nx.nro"
DOC = PROJECT / "docs/PERF34-DXVK-AB.md"

VARIANTS = {
    "dxvk-1103": {
        "label": "DXVK official 1.10.3",
        "archive": "dxvk-1.10.3.tar.gz",
        "url": "https://github.com/doitsujin/dxvk/releases/tag/v1.10.3",
    },
    "dxvk-sarek-1111": {
        "label": "DXVK-Sarek 1.11.1 Mali GPU Fix",
        "archive": "dxvk-sarek-v1.11.1-mali-fix.tar.gz",
        "url": "https://github.com/zeyadadev/DXVK-Sarek/releases/tag/v1.11.1-mali-fix",
    },
}

CURRENT = {
    "variant": "dxvk-current",
    "label": "Existing retained Wine-NX DXVK build",
    "source_archive": None,
    "source_url": "Wine-NX test-build-2 release payload / existing PERF34 CONFIG",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def x32_d3d9(archive: Path) -> tuple[bytes, str]:
    """Return the x86 D3D9 DLL and its archive member name."""
    with tarfile.open(archive, "r:gz") as tar:
        candidates = [
            m for m in tar.getmembers()
            if m.isfile() and m.name.lower().endswith("x32/d3d9.dll")
        ]
        if len(candidates) != 1:
            raise ValueError(f"Expected one x32/d3d9.dll in {archive}, found {candidates}")
        member = candidates[0]
        handle = tar.extractfile(member)
        if handle is None:
            raise ValueError(f"Unable to extract {member.name}")
        data = handle.read()

    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ValueError(f"{archive} does not contain a PE DLL")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"{archive} contains an invalid PE header")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    if machine != 0x14C:
        raise ValueError(f"{archive} x32 DLL has PE machine {machine:#x}, expected 0x14c")
    return data, member.name


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"Unsafe archive path: {name}")
            info = ZipInfo(name, (2026, 9, 23, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    raw = buffer.getvalue()
    with ZipFile(io.BytesIO(raw)) as check:
        if check.testzip() is not None:
            raise ValueError("Generated archive failed zip integrity check")
        if any(check.read(name) != value for name, value in files.items()):
            raise ValueError("Generated archive changed a payload member")
    return raw


def main() -> None:
    if not BASE.exists():
        raise FileNotFoundError(BASE)
    if not DOC.exists():
        raise FileNotFoundError(DOC)

    with ZipFile(BASE) as source:
        if source.testzip() is not None:
            raise ValueError("Existing PERF34 CONFIG archive is corrupt")
        base_manifest = json.loads(source.read("PERF34-manifest.json"))
        base = {
            name: source.read(name)
            for name in source.namelist()
            if name != "PERF34-manifest.json"
        }

    if DLL_PATH not in base or NRO_PATH not in base:
        raise ValueError("PERF34 CONFIG archive is missing the expected runtime files")
    base_nro_sha = sha(base[NRO_PATH])
    if base_nro_sha != base_manifest.get("nro_sha256"):
        raise ValueError("PERF34 NRO does not match its manifest")

    reports = []
    all_variants = [(CURRENT["variant"], CURRENT)] + list(VARIANTS.items())
    for variant, spec in all_variants:
        source_archive = SOURCE / spec["archive"] if spec.get("archive") else None
        if source_archive is None:
            dll = base[DLL_PATH]
            member = "PERF34 CONFIG:" + DLL_PATH
        else:
            if not source_archive.exists():
                raise FileNotFoundError(source_archive)
            dll, member = x32_d3d9(source_archive)
        payload = dict(base)
        for dll_path in DLL_PATHS:
            payload[dll_path] = dll
        metadata = {
            "variant": variant,
            "label": spec["label"],
            "source_archive": spec.get("archive"),
            "source_url": spec.get("url", CURRENT["source_url"]),
            "source_archive_sha256": sha(source_archive.read_bytes()) if source_archive else None,
            "source_member": member,
            "d3d9_sha256": sha(dll),
            "d3d9_bytes": len(dll),
            "pe_machine": "0x14c (x86)",
            "base_profile": "PERF34 CONFIG",
            "nro_sha256": base_nro_sha,
            "hardware_tested": False,
        }
        payload["DXVK-VARIANT.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
        payload["PERF34-DXVK-AB.md"] = DOC.read_bytes()
        manifest = {
            "variant": variant,
            "base": "PERF34 CONFIG",
            "abi": base_manifest.get("abi"),
            "nro_metadata": base_manifest.get("nro_metadata"),
            "nro_sha256": base_nro_sha,
            "hardware_tested": False,
            "target_verified": False,
            "changed_runtime_files": list(DLL_PATHS),
            "dxvk": metadata,
            "files": {name: sha(data) for name, data in sorted(payload.items())},
        }
        payload["PERF34-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
        raw = zip_bytes(payload)
        target = PROJECT / "dist" / f"pes13-perf34-{variant}.zip"
        # Never silently replace a package that was not created by this script.
        if target.exists():
            with ZipFile(target) as old:
                old_manifest = json.loads(old.read("PERF34-manifest.json"))
            if old_manifest.get("variant") != variant or old_manifest.get("base") != "PERF34 CONFIG":
                raise FileExistsError(f"Refusing to overwrite unrelated package: {target}")
        target.write_bytes(raw)
        with ZipFile(target) as check:
            assert check.testzip() is None
            assert sha(check.read(NRO_PATH)) == base_nro_sha
            assert sha(check.read(DLL_PATH)) == sha(dll)
        reports.append({
            "path": str(target),
            "variant": variant,
            "bytes": len(raw),
            "sha256": sha(raw),
            "nro_unchanged": True,
            "d3d9_sha256": sha(dll),
            "source_archive_sha256": metadata["source_archive_sha256"],
            "zip_integrity": True,
            "hardware_tested": False,
        })

    out = PROJECT / "local/dxvk-ab/packages.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
