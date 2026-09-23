"""Sample the existing PERF29 control without re-enabling worker growth."""
from pathlib import Path
import importlib.util
import io
import json
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recovery", PROJECT / "tools/package-perf29-recovery.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def sampling_files(control, enabled):
    keys = {recovery.FLAG, recovery.PROFILE, recovery.CONFIG}
    if not keys.issubset(control):
        raise ValueError("Missing control configuration")
    if control[recovery.FLAG] != b"0\n" or control[recovery.PROFILE] != b"0\n":
        raise ValueError("Expected quiet control with worker growth disabled")
    config = control[recovery.CONFIG]
    if config.splitlines().count(b"profile=0") != 1 or b"profile=1" in config:
        raise ValueError("Expected one disabled game profile setting")
    result = {name: control[name] for name in sorted(keys)}
    if enabled:
        result[recovery.PROFILE] = b"1\n"
        result[recovery.CONFIG] = b"".join(
            line.replace(b"profile=0", b"profile=1") if line.rstrip(b"\r\n") == b"profile=0" else line
            for line in config.splitlines(keepends=True))
    changed = {name for name in result if result[name] != control[name]}
    assert changed == ({recovery.PROFILE, recovery.CONFIG} if enabled else set())
    assert result[recovery.FLAG] == b"0\n"
    return result


def write_overlay(target, payload, enabled, nro_hash):
    files = dict(payload)
    files["PERF29-CONTROL-RESULT.md"] = (PROJECT / "docs/PERF29-CONTROL-RESULT.md").read_bytes()
    manifest = {
        "variant": "control-sampling" if enabled else "control-quiet", "abi": 4,
        "runtime_rebuilt": False, "hardware_tested": False, "nro_included": False,
        "requires_build": "pes13-nx-0.2.0-perf29-worker-blocks",
        "requires_nro_sha256": nro_hash, "scoped_worker_bigblock": 0,
        "cpu_sampling": enabled, "changes_from_quiet_control":
            [recovery.PROFILE, recovery.CONFIG] if enabled else [],
        "files": {name: recovery.digest(data) for name, data in files.items()}}
    files["PERF29-control-profile-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
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
        assert not any(name.endswith((".nro", ".exe", ".dll", "settings.dat", ".log")) for name in files)
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError(f"Refusing to overwrite different package: {target}")
    else:
        with target.open("xb") as output:
            output.write(raw)
    return {"path": str(target), "bytes": len(raw), "sha256": recovery.digest(raw),
            "worker_blocks": 0, "cpu_sampling": enabled, "zip_integrity": True,
            "runtime_rebuilt": False, "hardware_tested": False}


def main():
    original = recovery.load_pinned(PROJECT / "dist/pes13-perf29-worker-blocks.zip",
                                   "aaff5c547d7b631a3a8715654b5c810628620872ee8afd2766a847195a8140e0")
    quiet = recovery.load_pinned(PROJECT / "dist/pes13-perf29-control.zip",
                                "d2e6b746449de27e7e21afed1e667e1d0b6e6119e55c40cf5449ea373bcb49eb")
    old_sampling = recovery.load_pinned(PROJECT / "dist/pes13-perf29-sampling.zip",
                                       "ea2075e227f30ef9d8419f7718a5da97989c2dada6acea1e0bd64d1bbe0455ba")
    control = recovery.control_files(original, quiet)
    nro_hash = recovery.digest(control[recovery.PREFIX + "pes13-nx.nro"])
    assert nro_hash == "83a3b78018e4f01afd27d46cb67b5046552f9b1596d9fab7efb985b1e0622cc5"
    reports = []
    for enabled, label in ((True, "sampling"), (False, "quiet")):
        files = sampling_files(control, enabled)
        if enabled:
            assert files[recovery.CONFIG] == old_sampling[recovery.CONFIG]
            assert files[recovery.PROFILE] == old_sampling[recovery.PROFILE]
            assert files[recovery.FLAG] != old_sampling[recovery.FLAG]
        else:
            assert all(files[name] == quiet[name] for name in files)
        target = PROJECT / "dist" / f"pes13-perf29-control-{label}.zip"
        reports.append(write_overlay(target, files, enabled, nro_hash))
    evidence = PROJECT / "local/perf29/control-20260922"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "packages.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
