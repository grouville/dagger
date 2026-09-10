#!/usr/bin/env python3
"""Match a measured CLI process to its complete OTel trace for wcprof analysis."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processes", required=True, type=Path)
    parser.add_argument("--otel", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    processes = [json.loads(line) for line in args.processes.read_text().splitlines()]
    matches = [p for p in processes if p["label"] == args.label]
    if len(matches) != 1:
        parser.error(f"expected one process named {args.label}, found {len(matches)}")
    process = matches[0]
    start, end = process["start_unix_ns"], process["end_unix_ns"]

    # Live telemetry can export the same span more than once. Pick completed CLI
    # roots by identity, and refuse to silently combine independent sessions.
    roots = {}
    with args.otel.open() as source:
        for line in source:
            record = json.loads(line)
            if (record.get("kind") == "span" and record.get("scope") == "dagger.io/cli"
                    and not record.get("parentId") and record.get("endNs", 0) > 0
                    and start <= record["startNs"] <= record["endNs"] <= end):
                roots[record["traceId"], record["spanId"]] = record
    if len(roots) != 1:
        parser.error(f"expected one completed CLI root inside process interval, found {len(roots)}")
    root = next(iter(roots.values()))
    if args.output.resolve() in (args.otel.resolve(), args.processes.resolve()):
        parser.error("output must not overwrite an input")

    # Exclusive creation protects earlier captures. Keep all records of this
    # trace, including live starts, logs and wcprof completeness markers.
    with args.output.open("x") as output, args.otel.open() as source:
        for line in source:
            if json.loads(line).get("traceId") == root["traceId"]:
                output.write(line)
    print(json.dumps({
        "label": args.label,
        "trace_id": root["traceId"],
        "process_ms": process["milliseconds"],
        "before_root_ms": (root["startNs"] - start) / 1e6,
        "root_ms": (root["endNs"] - root["startNs"]) / 1e6,
        "after_root_ms": (end - root["endNs"]) / 1e6,
        "wall_minus_monotonic_ms": (end - start) / 1e6 - process["milliseconds"],
        "exit_code": process["exit_code"],
        "note": "Run the wcprof OTel structural gate on the extracted trace before interpreting rankings.",
    }, indent=2))


if __name__ == "__main__":
    main()
