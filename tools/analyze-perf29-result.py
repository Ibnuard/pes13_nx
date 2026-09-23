"""Summarize mixed-build evidence without counting rotated logs as new trials."""
from pathlib import Path
import argparse
import hashlib
import json
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def numbers(line):
    return {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)(?=\s|;|$)", line)}


def parse(path):
    raw = path.read_bytes()
    run = {"file": path.name, "bytes": len(raw), "sha256": digest(raw),
           "build": [], "sampler": [], "rows": [], "progress": [], "faults": [],
           "worker_blocks": None, "lifecycle": [], "sampler_status": []}
    row = None
    for line_number, line in enumerate(raw.decode(errors="replace").splitlines(), 1):
        if line.startswith("[BUILD] "):
            run["build"].append(line.split(" ", 1)[1])
        elif line.startswith("[PERF24]") and "CPU sampler=" in line:
            run["sampler"].append(line.split("CPU sampler=", 1)[1].split(";", 1)[0])
        elif line.startswith("[PERF8]"):
            row = numbers(line)
            row.update({"frames": {}, "pipe": {}, "threads": {}, "profiles": {}})
            run["rows"].append(row)
        elif line.startswith("[PERF29]"):
            run["worker_blocks"] = numbers(line)
            if row is not None:
                row["worker_blocks"] = numbers(line)
        elif line.startswith("[FRAME24]") and row is not None and " bins=" in line:
            frame = numbers(line)
            frame["bins"] = list(map(int, line.split("bins=", 1)[1].split(",")))
            if len(frame["bins"]) != 10 or sum(frame["bins"]) != frame["n"]:
                raise ValueError(f"Invalid histogram in {path.name}: {line}")
            row["frames"][line.split()[1]] = frame
        elif line.startswith("[PIPE27]") and row is not None:
            row["pipe"][line.split()[1]] = numbers(line)
        elif line.startswith("[THREADS]") and row is not None:
            row["threads"] = {thread: float(percent) for thread, percent in
                              re.findall(r"(\d+[ws])@-?\d+ ([\d.]+)%", line)}
            row["cores"] = float(re.search(r"use ([\d.]+) cores", line)[1])
        elif line.startswith("[SAMPLE24]") and row is not None:
            row["sampling"] = numbers(line)
        elif line.startswith("[PROF]"):
            match = re.match(r"\[PROF\] (\d+[ws]) samples=(\d+) missed=(\d+) (.*)", line)
            sites = re.match(r"\[PROF\] (\d+[ws]) ([\w ]+): (.*)", line)
            if match and row is not None:
                row["profiles"][match[1]] = {
                    "samples": int(match[2]), "missed": int(match[3]), "sites": {},
                    "shares": {key: float(value) for key, value in
                               re.findall(r"(\w+)=([\d.]+)%", match[4])}}
            elif sites and row is not None and sites[1] in row["profiles"]:
                row["profiles"][sites[1]]["sites"][sites[2]] = {
                    address: float(percent) for address, percent in
                    re.findall(r"(\S+) ([\d.]+)%", sites[3])}
            else:
                run["sampler_status"].append(line)
        elif line.startswith(("[THREAD]", "[LIFECYCLE]")):
            run["lifecycle"].append({"line": line_number, "text": line,
                                     "after_perf8_uptime_s": row["uptime_s"] if row else None})
        elif line.startswith("[PROGRESS]"):
            progress = numbers(line)
            progress["progress_elapsed_s"] = int(re.search(r"\[PROGRESS\] (\d+)s", line)[1])
            progress["after_perf8_uptime_s"] = row["uptime_s"] if row else None
            run["progress"].append(progress)
        elif line.startswith(("[BOX64 FAULT]", "[EXIT]")) or (
                line.startswith("[FAULT28]") and any(marker in line for marker in
                ("begin read-only", " eip=", " inferred table=", " end scanned="))):
            run["faults"].append(line)
    return run


def summarize(rows, low, high):
    selected = [row for row in rows if low <= row["uptime_s"] <= high]
    interval_ms = sum(row["interval_ms"] for row in selected)
    result = {"windows_ending_s": [row["uptime_s"] for row in selected],
              "presents": sum(row["presents"] for row in selected),
              "interval_ms": interval_ms, "frames": {}, "pipe": {}}
    result["presents_per_s"] = result["presents"] * 1000 / interval_ms if interval_ms else None
    for phase in sorted({phase for row in selected for phase in row["frames"]}):
        frames = [row["frames"][phase] for row in selected if phase in row["frames"]]
        count = sum(frame["n"] for frame in frames)
        bins = [sum(frame["bins"][index] for frame in frames) for index in range(10)]
        result["frames"][phase] = {
            "n": count, "bins": bins,
            "avg_us": sum(frame["n"] * frame["avg_us"] for frame in frames) / count if count else None,
            "over_500ms": sum(bins[7:]), "over_1000ms": sum(bins[8:]),
            "max_since_launch_us": max(frame["max_since_launch_us"] for frame in frames)}
    for stage in sorted({stage for row in selected for stage in row["pipe"]}):
        spans = [row["pipe"][stage] for row in selected if stage in row["pipe"]]
        count = sum(span["n"] for span in spans)
        total_us = sum(span["total_us"] for span in spans)
        result["pipe"][stage] = {
            "n": count, "total_us": total_us, "avg_us": total_us / count if count else None,
            "gt16ms": sum(span["gt16ms"] for span in spans),
            "max_since_launch_us": max(span["max_since_launch_us"] for span in spans)}
    return result


def analyze(source, prior):
    old_hashes = {}
    for path in sorted(prior.glob("*.log")):
        old_hashes.setdefault(digest(path.read_bytes()), []).append(path.name)
    runs = []
    for path in sorted(source.glob("*.log")):
        run = parse(path)
        run["identical_prior_files"] = old_hashes.get(run["sha256"], [])
        run["windows"] = {label: summarize(run["rows"], low, high) for label, low, high in (
            ("ending_90_100", 90, 100), ("ending_110_120", 110, 120),
            ("ending_110_150", 110, 150), ("ending_170_330", 170, 330),
            ("ending_120_170", 120, 170), ("ending_160_170", 160, 170),
            ("ending_180", 180, 180))}
        runs.append(run)
    if not runs:
        raise ValueError(f"No logs in {source}")
    return {"runs": runs, "limits": [
        "Rotated logs with identical bytes are historical, not new controls.",
        "Present rate does not measure simulation speed or detect duplicate frame content.",
        "Scene transitions and clocks are not independently synchronized between runs.",
        "PIPE27 measures host wall time, not GPU execution; spans can overlap across threads.",
        "max_since_launch_us is cumulative, not restricted to each selected window.",
        "PERF29 selected/completed count compilations, not executions or saved CPU time.",
        "PROGRESS uses a separate clock; audio_under counts empty-queue observations, not unique audible gaps.",
        "Lifecycle positions only bracket log order, not exact event times or foul/replay scene labels.",
        "CPU samples include blocked time; targets follow the preceding CPU report and can miss short-lived workers.",
        "No timed audio-buffer content, producer-latency or echo capture is available."]}


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--prior", type=Path, default=project / "local/perf29/results")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.source, args.prior)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for run in report["runs"]:
        last = run["rows"][-1]["uptime_s"] if run["rows"] else None
        print(f'{run["file"]}: build={run["build"]}, sampler={run["sampler"]}, '
              f'last_perf8={last}, prior={run["identical_prior_files"]}')


if __name__ == "__main__":
    main()
