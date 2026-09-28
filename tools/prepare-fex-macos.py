#!/usr/bin/env python3
"""Reconstruct FEX3 Wine snapshots; source-only, no compiler or SDK required.

The historical PERF11 recipes restore their baseline in finally blocks. FEX
needs the bootstrap-wsl.sh baseline (wine-nx.patch plus five source overlays),
NOT PERF8/PERF11/PERF15 generated output or a Box64 vendor checkout. Keep both
runtime build-ID branches: the existing FEX patcher replaces the console one.

Example:
    python3 tools/prepare-fex-macos.py --build-root "$PES_BUILD_ROOT"

Existing master patchers remain authoritative. Receipts use the same files /
origin schema as fex2_prepare so build-fex-runtime can reuse these snapshots.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

PIN = "1bc4e45163f0d2328cdfd35c7f471dd9821bb879"
OVERLAYS = {
    "pes13_preload.c": "wine-nx-probe/source/pes13_preload.c",
    "pes13_graphics.h": "wine-nx-probe/source/pes13_graphics.h",
    "pes13_controller.h": "wine-nx-probe/source/pes13_controller.h",
    "pes13_controller_ui.h": "wine-nx-probe/source/pes13_controller_ui.h",
    "pes13_registry.h": "dlls/ntdll/unix/pes13_registry.h",
}


def export_pinned(source, destination, revision):
    """Export Git objects, not workspace files; no hardlinks or Git metadata."""
    source, destination = Path(source), Path(destination)
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != revision:
        raise RuntimeError(f"Unexpected Wine revision: {head}; expected {revision}")
    destination.mkdir()
    with tempfile.TemporaryFile() as archive:
        subprocess.run(["git", "-C", str(source), "archive", revision],
                       stdout=archive, check=True)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tar:
            tar.extractall(destination, filter="data")
    return {"commit": revision, "source": str(source.resolve())}


def file_hashes(directory):
    """Match the fex2_prepare manifest schema; exclude Git and Python caches."""
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob("*"))
            if path.is_file() and not path.is_symlink()
            and not {".git", "__pycache__"}.intersection(path.relative_to(directory).parts)}


def prepare(root, source, project):
    root, source, project = (Path(path).resolve() for path in (root, source, project))
    lock = json.loads((project / "dependencies.json").read_text())["wine_nx"]
    if lock["commit"] != PIN:
        raise RuntimeError("Wine dependency pin changed; audit preparation before use")
    root.mkdir(parents=True, exist_ok=True)
    baseline = root / "runtime-perf11-source"
    work = root / "fex-experiment/wine3"
    if baseline.exists() or work.exists():
        raise RuntimeError("Existing preparation paths; refusing to overwrite")
    with tempfile.TemporaryDirectory(prefix=".prepare-fex-macos-", dir=root) as temporary:
        stage = Path(temporary)
        base = stage / "runtime-perf11-source"
        wine = export_pinned(source, base, PIN)
        wine["repository"] = lock["repository"]
        wine["tree"] = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", PIN + "^{tree}"], text=True).strip()
        wine["patches"] = ["patches/wine-nx.patch"]
        patch = project / wine["patches"][0]
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=base, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=base, check=True)
        for name, target in OVERLAYS.items():
            shutil.copyfile(project / "src/runtime" / name, base / target)
        base_hashes = file_hashes(base)
        staged_work = stage / "wine3"
        staged_work.mkdir()
        shutil.copytree(base, staged_work / "native-source", symlinks=True)
        export_pinned(source, staged_work / "pe-source", PIN)
        for kind, origin in (("native-source", baseline), ("pe-source", source)):
            stamp = {"origin": str(origin), "files": file_hashes(staged_work / kind)}
            (staged_work / (kind + ".json")).write_text(json.dumps(stamp, indent=2) + "\n")
        sys.path.insert(0, str(project / "tools"))
        from fex_wine_patches import apply
        patches = apply(staged_work, project, integration=True)
        if patches != apply(staged_work, project, integration=True):
            raise RuntimeError("FEX master integration is not idempotent")
        report = {"wine": wine, "baseline": str(baseline), "work": str(work),
                  "native_source": str(work / "native-source"),
                  "pe_source": str(work / "pe-source"),
                  "baseline_files": base_hashes,
                  "files": {kind: file_hashes(staged_work / kind)
                            for kind in ("native-source", "pe-source")},
                  "integration_patch_counts": {kind: len(files) for kind, files in patches.items()},
                  "integration_idempotent": True, "compiled": False,
                  "box64_vendor_required": False,
                  "required_cmake_options": {"WINE_NX_BOX64_DYNAREC": "OFF",
                                             "WINE_NX_BOX64_INTERPRETER": "OFF"}}
        (staged_work / "prepare-fex-macos.json").write_text(json.dumps(report, indent=2) + "\n")
        work.parent.mkdir(parents=True, exist_ok=True)
        base.rename(baseline)
        staged_work.rename(work)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path,
                        default=Path(os.environ.get("PES_BUILD_ROOT", str(Path.home() / ".cache/pes13-nx-macos"))))
    parser.add_argument("--source", type=Path, help="Original pinned Git clone; default BUILD_ROOT/source")
    args = parser.parse_args()
    report = prepare(args.build_root, args.source or args.build_root / "source", Path(__file__).resolve().parents[1])
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("files", "baseline_files")}, indent=2))


if __name__ == "__main__":
    main()
