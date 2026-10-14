#!/usr/bin/env python3
"""Profile fresh no-op executions on a warm Dagger engine."""

import argparse
import json
from pathlib import Path
import secrets
import statistics
import subprocess
import time
import urllib.request


def query(image, mode):
    nonce = secrets.token_hex(12)

    def action(index):
        arguments = json.dumps(["/usr/bin/true", nonce, str(index)])
        return f"withExec(args:{arguments},disableDaggerInDagger:true)"

    container = "container{from(address:" + json.dumps(image) + "){"
    if mode == "one":
        return "{" + container + action(0) + "{sync}}}}"
    if mode == "sequential":
        return "{" + container + action(0) + "{" + action(1) + "{sync}}}}}"
    return "{a:" + container + action(0) + "{sync}}} b:" + container + action(1) + "{sync}}}}"


def pressure():
    return {
        name: int(Path("/proc/pressure", name).read_text().splitlines()[0].split("total=")[1])
        for name in ["cpu", "io"]
    }


def measure(endpoint, output, command, image, label, mode):
    def debug(route, body=None):
        request = urllib.request.Request(endpoint + "/debug/wcprof/" + route, data=body)
        return urllib.request.urlopen(request, timeout=30)

    document = output / (label + ".graphql")
    document.write_text(query(image, mode) + "\n")
    with debug("enabled") as response:
        if json.load(response)["global_enabled"]:
            raise RuntimeError("wcprof is already recording; use an idle, isolated engine")
    debug("enabled", b"on").close()
    try:
        with debug("dump") as response:
            while response.read(1024 * 1024):
                pass
        start_pressure = pressure()
        started = time.monotonic()
        with (output / (label + ".log")).open("w") as log:
            result = subprocess.run(
                command + ["api", "query", "--doc", str(document)],
                stdout=log, stderr=subprocess.STDOUT,
            )
        elapsed = time.monotonic() - started
        end_pressure = pressure()
    finally:
        debug("enabled", b"off").close()
        with debug("dump") as response, (output / (label + ".ndjson")).open("wb") as dump:
            while chunk := response.read(1024 * 1024):
                dump.write(chunk)
    if result.returncode:
        raise RuntimeError(f"{label} failed; see {output / (label + '.log')}")
    with (output / (label + ".ndjson")).open() as dump:
        header = json.loads(next(dump))
        if header["schema_version"] != 1 or header["dropped_events"] or header.get("open_ops"):
            raise RuntimeError(f"{label}: incomplete or unsupported recording")
        operations = [json.loads(line) for line in dump]

    def events(name):
        return [
            event for event in operations
            if event["e"] == "op" and header["strings"][event.get("c", 0)] == name
        ]

    count = 1 if mode == "one" else 2
    runtime = events("exec.runtimeStart")
    executions = events("exec.run")
    if len(runtime) != count or len(executions) != count:
        raise RuntimeError(f"{label}: expected {count} fresh processes")
    if any(event.get("o") != "ok" for event in executions):
        raise RuntimeError(f"{label}: execution failed")
    return {
        "label": label, "mode": mode, "cli_seconds": elapsed,
        "exec_span_ms": (
            max(event["d"] for event in executions) - min(event["s"] for event in executions)
        ) / 1e6,
        "runtime_start_ms": [(event["d"] - event["s"]) / 1e6 for event in runtime],
        "phase_totals_ms": {
            name: sum(event["d"] - event["s"] for event in events("exec." + name)) / 1e6
            for name in ["runtimeStart", "setupRootfs", "setupNetwork", "containerStart",
                         "initStart", "processSpawn", "workload", "processExit"]
        },
        "pressure_fraction": {
            name: (end_pressure[name] - start_pressure[name]) / (elapsed * 1e6)
            for name in start_pressure
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--image", required=True, help="image providing /usr/bin/true")
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="CLI command after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.runs < 1:
        parser.error("supply a CLI command after -- and a positive run count")
    output = args.out.resolve()
    if output.is_relative_to(Path.cwd().resolve()):
        parser.error("keep captures outside the workspace, for example under /tmp")
    output.mkdir(parents=True, exist_ok=False)
    endpoint = args.debug_url.rstrip("/")
    modes = ["one", "sequential", "parallel"]
    for mode in modes:
        measure(endpoint, output, command, args.image, "prepare-" + mode, mode)
    rows = []
    for index in range(args.runs):
        for mode in modes if index % 2 == 0 else list(reversed(modes)):
            row = measure(endpoint, output, command, args.image, f"{index}-{mode}", mode)
            rows.append(row)
            (output / "samples.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(f"{row['label']}: execution span {row['exec_span_ms']:.2f} ms", flush=True)
    summary = {
        mode: {
            "exec_span_ms": statistics.median(row["exec_span_ms"] for row in rows if row["mode"] == mode),
            "runtime_start_total_ms": statistics.median(
                sum(row["runtime_start_ms"]) for row in rows if row["mode"] == mode
            ),
            "cli_seconds": statistics.median(row["cli_seconds"] for row in rows if row["mode"] == mode),
        }
        for mode in modes
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
