"""Create reversible PERF34 scheduler A/B overlays.

The overlays reuse the verified PERF34 NRO and change only configuration.ini;
they never rebuild or replace the runtime binary.  Refuse to overwrite an
existing archive so a hardware result cannot be silently lost.
"""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import json


PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "dist/pes13-perf34-config.zip"
PREFIX = "switch/pes13-nx/"
CONFIG_PATH = PREFIX + "configuration.ini"
DOC_PATH = "PERF34-BALANCE-AB.md"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_config(config: bytes, *, secondary: int, all_balance: int,
                  extra: dict[str, int] | None = None) -> bytes:
    extra = extra or {}
    text = config.decode("utf-8")
    lines = []
    seen = set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        if key == "perf23_balance":
            line = f"perf23_balance={secondary}"
        elif key == "no_balance":
            line = f"no_balance={all_balance}"
        elif key in extra:
            line = f"{key}={extra[key]}"
        if key in {"perf23_balance", "no_balance", *extra}:
            seen.add(key)
        lines.append(line)
    assert seen == {"perf23_balance", "no_balance", *extra}
    return ("\n".join(lines) + "\n").encode("utf-8")


def package(variant: str, config: bytes, base_manifest: dict) -> dict:
    with ZipFile(BASE) as source:
        source.testzip()
        payload = {name: source.read(name) for name in source.namelist()
                   if name != "PERF34-manifest.json"}
    assert CONFIG_PATH in payload
    nro_name = PREFIX + "pes13-nx.nro"
    assert sha(payload[nro_name]) == base_manifest["nro_sha256"]
    payload[CONFIG_PATH] = config
    payload[DOC_PATH] = (PROJECT / "docs" / DOC_PATH).read_bytes()
    manifest = {
        "variant": variant,
        "base": "PERF34 CONFIG",
        "abi": base_manifest["abi"],
        "nro_metadata": base_manifest["nro_metadata"],
        "nro_sha256": sha(payload[nro_name]),
        "hardware_tested": False,
        "target_verified": False,
        "requires": "Existing PES13 installation and PERF34-compatible SD layout",
        "changed_runtime_files": [CONFIG_PATH],
        "scheduler_experiment": True,
        "files": {name: sha(data) for name, data in sorted(payload.items())},
    }
    payload["PERF34-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    target = PROJECT / "dist" / f"pes13-perf34-{variant}.zip"
    raw = None
    import io
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = ZipInfo(name, (2026, 9, 23, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    raw = buf.getvalue()
    with ZipFile(io.BytesIO(raw)) as check:
        assert check.testzip() is None
        assert check.read(CONFIG_PATH) == config
        assert sha(check.read(nro_name)) == base_manifest["nro_sha256"]
    if target.exists():
        # Only replace an archive previously emitted by this script.  A file
        # with the same name from another build remains protected.
        with ZipFile(target) as old:
            old_manifest = json.loads(old.read("PERF34-manifest.json"))
        assert old_manifest.get("scheduler_experiment") is True
        assert old_manifest.get("nro_sha256") == base_manifest["nro_sha256"]
    target.write_bytes(raw)
    return {"path": str(target), "variant": variant, "bytes": len(raw),
            "sha256": sha(raw), "nro_unchanged": True,
            "configuration_sha256": sha(config)}


def main() -> None:
    assert BASE.exists(), BASE
    with ZipFile(BASE) as archive:
        base_manifest = json.loads(archive.read("PERF34-manifest.json"))
        original = archive.read(CONFIG_PATH)
    results = [
        package("secondary-off", update_config(original, secondary=0, all_balance=0), base_manifest),
        package("balance-off", update_config(original, secondary=0, all_balance=1), base_manifest),
        package("cache-ab", update_config(original, secondary=1, all_balance=0,
                                          extra={"gl_clean_test": 1}), base_manifest),
        package("gl-noclean", update_config(original, secondary=1, all_balance=0,
                                             extra={"gl_noclean": 1}), base_manifest),
    ]
    out = PROJECT / "local/perf34/balance-ab-packages.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
