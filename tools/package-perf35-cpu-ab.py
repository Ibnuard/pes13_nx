"""Build isolated PERF35 CPU/pipeline experiments over the stable DXVK base."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "dist/pes13-perf34-dxvk-current.zip"
PREFIX = "switch/pes13-nx/"
NRO = PREFIX + "pes13-nx.nro"
BOX64 = PREFIX + "drive_c/PES13/pes2013.box64.txt"
CONFIG = PREFIX + "configuration.ini"
DXVK_CONF = PREFIX + "drive_c/PES13/dxvk.conf"
DLLS = (PREFIX + "drive_c/PES13/d3d9.dll", PREFIX + "drive_c/dxvk/d3d9.dll")
DOC = PROJECT / "docs/PERF35-CPU.md"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_box64(text: str, values: dict[str, int]) -> bytes:
    lines = []
    seen = set()
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _ = line.split("=", 1)
            key = key.strip()
            short = key.removeprefix("BOX64_DYNAREC_")
            if short in values:
                line = f"{key}={values[short]}"
                seen.add(short)
        lines.append(line)
    if seen != set(values):
        raise ValueError(f"Box64 keys not found: {set(values) - seen}")
    return ("\n".join(lines) + "\n").encode()


def replace_ini(data: bytes, key: str, value: int) -> bytes:
    lines, seen = [], False
    for line in data.decode().splitlines():
        if line.split("=", 1)[0].strip() == key:
            line = f"{key}={value}"
            seen = True
        lines.append(line)
    if not seen:
        raise ValueError(f"INI key not found: {key}")
    return ("\n".join(lines) + "\n").encode()


def write_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, (2026, 9, 23, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            z.writestr(info, data)
    raw = buf.getvalue()
    with ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        assert all(z.read(name) == data for name, data in files.items())
    return raw


def main() -> None:
    if not BASE.exists() or not DOC.exists():
        raise FileNotFoundError(BASE if not BASE.exists() else DOC)
    with ZipFile(BASE) as z:
        assert z.testzip() is None
        base_manifest = json.loads(z.read("PERF34-manifest.json"))
        base = {n: z.read(n) for n in z.namelist() if n != "PERF34-manifest.json"}
    base_nro = sha(base[NRO])
    assert base_nro == base_manifest["nro_sha256"]
    original_box = base[BOX64].decode()
    original_ini = base[CONFIG]

    variants = {
        "perf35-cpu-global": {
            "label": "Global Box64 aggressive CPU policy",
            "box64": {"FASTNAN": 1, "FASTROUND": 1, "BIGBLOCK": 3, "STRONGMEM": 0},
            "ini": original_ini,
            "dxvk": b"d3d9.maxFrameRate = -1\n",
            "risk": "high; broadens PERF33's scoped flags to the whole process",
        },
        "perf35-cpu-quiet": {
            "label": "Quiet CPU/compiler contention policy",
            "box64": {},
            "ini": replace_ini(original_ini, "perf17_capture", 0),
            "dxvk": (
                b"d3d9.maxFrameRate = -1\n"
                b"dxvk.numCompilerThreads = 1\n"
                b"d3d9.deviceLocalConstantBuffers = False\n"
            ),
            "risk": "low; keeps the tested Box64 policy and changes only capture/compiler work",
        },
    }

    reports = []
    for variant, spec in variants.items():
        files = dict(base)
        files[BOX64] = replace_box64(original_box, spec["box64"]) if spec["box64"] else base[BOX64]
        files[CONFIG] = spec["ini"]
        files[DXVK_CONF] = spec["dxvk"]
        metadata = {
            "variant": variant,
            "label": spec["label"],
            "base": "PERF34 DXVK current",
            "risk": spec["risk"],
            "nro_sha256": base_nro,
            "changed_files": ([BOX64, DXVK_CONF] if spec["box64"] else
                              [CONFIG, DXVK_CONF]),
            "hardware_tested": False,
        }
        files["PERF35-CPU.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
        files["PERF35-CPU.md"] = DOC.read_bytes()
        manifest = {
            "variant": variant,
            "base": "PERF34 DXVK current",
            "abi": base_manifest.get("abi"),
            "nro_metadata": base_manifest.get("nro_metadata"),
            "nro_sha256": base_nro,
            "hardware_tested": False,
            "target_verified": False,
            "changed_runtime_files": metadata["changed_files"],
            "files": {n: sha(v) for n, v in sorted(files.items())},
        }
        files["PERF35-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
        raw = write_zip(files)
        target = PROJECT / "dist" / f"{variant}.zip"
        if target.exists():
            with ZipFile(target) as old:
                old_m = json.loads(old.read("PERF35-manifest.json"))
            if old_m.get("variant") != variant:
                raise FileExistsError(target)
        target.write_bytes(raw)
        with ZipFile(target) as check:
            assert check.testzip() is None
            assert sha(check.read(NRO)) == base_nro
            assert check.read(DLLS[0]) == check.read(DLLS[1])
        reports.append({"path": str(target), "variant": variant, "bytes": len(raw),
                        "sha256": sha(raw), "nro_unchanged": True,
                        "hardware_tested": False})
    out = PROJECT / "local/perf35-cpu/packages.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
