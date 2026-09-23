"""Package the PERF35 source-level NRO over the stable PERF34 DXVK base."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from nro_assets import inspect_nro

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "dist/pes13-perf34-dxvk-current.zip"
PAYLOAD = PROJECT / "local/perf35/payload/switch/pes13-nx/pes13-nx.nro"
DOC = PROJECT / "docs/PERF35-FAST-JUMPTABLE.md"
PREFIX = "switch/pes13-nx/"
NRO = PREFIX + "pes13-nx.nro"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    assert BASE.exists() and PAYLOAD.exists() and DOC.exists()
    status = json.loads((PROJECT / "local/perf35/build-status.json").read_text())
    assert status == {"state": "complete", "restored": True}, status
    verify = json.loads((PROJECT / "local/perf35/verification.json").read_text())
    assert verify["source_cleanup"] is True
    assert verify["save_mem"] is False
    assert verify["hot_diagnostic_atomics"] is False

    nro = PAYLOAD.read_bytes()
    assert b"pes13-nx-0.2.0-perf35-fast-jumptable" in nro
    metadata = inspect_nro(
        nro, (PROJECT / "assets/icon.jpg").read_bytes(),
        expected_title="PES13-NX PERF35 FAST JUMPTABLE",
    )
    with ZipFile(BASE) as z:
        assert z.testzip() is None
        old_manifest = json.loads(z.read("PERF34-manifest.json"))
        files = {name: z.read(name) for name in z.namelist()
                 if name != "PERF34-manifest.json"}
    old_nro = files[NRO]
    assert sha(old_nro) == old_manifest["nro_sha256"]
    files[NRO] = nro
    files["PERF35-FAST-JUMPTABLE.md"] = DOC.read_bytes()
    files["PERF35-FAST-JUMPTABLE.json"] = (json.dumps({
        "variant": "perf35-fast-jumptable",
        "base": "PERF34 DXVK current",
        "changed_runtime_files": [NRO],
        "nro_sha256": sha(nro),
        "old_nro_sha256": sha(old_nro),
        "save_mem": False,
        "hot_diagnostic_atomics": False,
        "source_cleanup_new_vs_perf34": False,
        "box64_preset_unchanged": True,
        "dxvk_unchanged": True,
        "target_match_fps": 30,
        "target_verified": False,
        "hardware_tested": False,
    }, indent=2) + "\n").encode()
    manifest = {
        "variant": "perf35-fast-jumptable",
        "base": "PERF34 DXVK current",
        "abi": old_manifest.get("abi"),
        "nro_metadata": metadata,
        "nro_sha256": sha(nro),
        "old_nro_sha256": sha(old_nro),
        "hardware_tested": False,
        "target_verified": False,
        "changed_runtime_files": [NRO],
        "dxvk": old_manifest.get("dxvk"),
        "source_cleanup": {"save_mem": False, "hot_diagnostic_atomics": False,
                           "new_vs_perf34": False},
        "files": {},
    }
    manifest["files"] = {name: sha(data) for name, data in sorted(files.items())}
    files["PERF35-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()

    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            assert not name.startswith("/") and ".." not in Path(name).parts
            info = ZipInfo(name, (2026, 9, 23, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            z.writestr(info, data)
    raw = buf.getvalue()
    target = PROJECT / "dist/perf35-fast-jumptable.zip"
    target.write_bytes(raw)
    with ZipFile(target) as z:
        assert z.testzip() is None
        assert sha(z.read(NRO)) == sha(nro)
        assert z.read(PREFIX + "drive_c/PES13/d3d9.dll") == z.read(PREFIX + "drive_c/dxvk/d3d9.dll")
    report = {
        "path": str(target), "bytes": len(raw), "sha256": sha(raw),
        "nro_sha256": sha(nro), "base_nro_sha256": sha(old_nro),
        "nro_only_change": True, "hardware_tested": False,
    }
    (PROJECT / "local/perf35/packages.json").write_text(
        json.dumps([report], indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
