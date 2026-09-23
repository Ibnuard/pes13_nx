"""Repack the pinned PERF29 main build with its single-variable control."""
from pathlib import Path
import hashlib
import io
import json
import zipfile
from nro_assets import inspect_nro

PREFIX = "switch/pes13-nx/"
FLAG = PREFIX + "perf29-worker-blocks.txt"
PROFILE = PREFIX + "profile.txt"
CONFIG = PREFIX + "drive_c/PES13/pes2013.wine-nx.txt"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_pinned(path, expected):
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError(f"Unexpected archive hash: {path}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files.pop("PERF29-manifest.json"))
    assert set(files) == set(manifest["files"])
    assert all(digest(data) == manifest["files"][name] for name, data in files.items())
    return files


def control_files(main, overlay):
    payload = {name: data for name, data in main.items() if name.startswith(PREFIX)}
    control = {name: data for name, data in overlay.items() if name.startswith(PREFIX)}
    assert set(control) == {FLAG, PROFILE, CONFIG}
    assert payload[FLAG] == b"1\n" and control[FLAG] == b"0\n"
    assert payload[PROFILE] == control[PROFILE] == b"0\n"
    assert payload[CONFIG] == control[CONFIG]
    assert control[CONFIG].count(b"profile=0") == 1 and b"profile=1" not in control[CONFIG]
    recovered = dict(payload)
    recovered.update(control)
    assert [name for name in payload if payload[name] != recovered[name]] == [FLAG]
    assert sum(name.endswith(".nro") for name in recovered) == 1
    assert not any(name.lower().endswith((".exe", "settings.dat", ".log")) for name in recovered)
    return recovered


def main():
    project = Path(__file__).resolve().parents[1]
    original = load_pinned(project / "dist/pes13-perf29-worker-blocks.zip",
                          "aaff5c547d7b631a3a8715654b5c810628620872ee8afd2766a847195a8140e0")
    overlay = load_pinned(project / "dist/pes13-perf29-control.zip",
                         "d2e6b746449de27e7e21afed1e667e1d0b6e6119e55c40cf5449ea373bcb49eb")
    files = control_files(original, overlay)
    nro = files[PREFIX + "pes13-nx.nro"]
    metadata = inspect_nro(nro, (project / "assets/icon.jpg").read_bytes(),
                           expected_title="PES13-NX PERF29")
    assert nro == original[PREFIX + "pes13-nx.nro"]
    assert b"pes13-nx-0.2.0-perf29-worker-blocks" in nro
    files.update({name: data for name, data in original.items() if name.startswith("licenses/")})
    for name in ("PERF29.md", "PERF29-RESULT.md"):
        files[name] = (project / "docs" / name).read_bytes()
    manifest = {"variant": "control-full", "abi": 4, "hardware_tested": False,
                "runtime_rebuilt": False, "only_runtime_change": FLAG,
                "cpu_sampling": False, "scoped_worker_bigblock": 0,
                "requires": "Existing PES13 installation; includes exact PERF29 NRO",
                "nro_sha256": digest(nro), "nro_metadata": metadata,
                "files": {name: digest(data) for name, data in files.items()}}
    files["PERF29-control-full-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 9, 22, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    raw = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None and set(archive.namelist()) == set(files)
        assert all(archive.read(name) == data for name, data in files.items())
    target = project / "dist/pes13-perf29-control-full.zip"
    if target.exists():
        assert target.read_bytes() == raw, f"Refusing to overwrite different package: {target}"
    else:
        with target.open("xb") as output:
            output.write(raw)
    report = {"path": str(target), "bytes": len(raw), "sha256": digest(raw),
              "single_variable_control": True, "same_nro": True,
              "zip_integrity": True, "hardware_tested": False}
    evidence = project / "local/perf29/regression-20260922"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "package.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
