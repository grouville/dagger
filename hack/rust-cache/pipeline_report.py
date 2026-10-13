#!/usr/bin/env python3
"""Inspect Cargo's observed metadata overlap and compiler-only dependency paths."""

import argparse
import json
from pathlib import Path


def analyze(plan):
    actions = {action["id"]: {**action, "dependencies": action.get("dependencies") or []}
               for action in plan["actions"]}
    if not actions:
        raise ValueError("no compiler actions to analyze")
    remaining = dict(actions)
    full, metadata, pipelined, ancestors = {}, {}, {}, {}
    overlap = []
    while remaining:
        ready = [action for action in remaining.values() if all(dep in full for dep in action["dependencies"])]
        if not ready:
            raise ValueError("compiler dependency graph contains missing actions or a cycle")
        for action in ready:
            identifier = action["id"]
            duration = action.get("compiler_seconds", 0)
            metadata_duration = action.get("metadata_seconds", 0)
            if duration <= 0:
                raise ValueError("capture lacks compiler timings; recapture with the current wrapper")
            is_library = any(output.endswith(".rmeta") for output in action["outputs"])
            uses_metadata = is_library and not any(arg.endswith(".rlib") for arg in action.get("args", []))
            if is_library and not 0 < metadata_duration <= duration:
                raise ValueError("capture lacks early metadata timings; recapture with the current wrapper")
            parents = action["dependencies"]
            ancestors[identifier] = set(parents)
            for dep in parents:
                ancestors[identifier].update(ancestors[dep])
            full[identifier] = duration + max((full[dep] for dep in parents), default=0)
            required = parents if uses_metadata else ancestors[identifier]
            start = max(((metadata if uses_metadata else pipelined)[dep] for dep in required), default=0)
            pipelined[identifier] = start + duration
            metadata[identifier] = start + (metadata_duration if is_library else duration)
            began = action.get("compiler_started_unix_nanos", 0) / 1e9
            for dep in parents:
                producer = actions[dep]
                producer_started = producer.get("compiler_started_unix_nanos", 0) / 1e9
                if began and producer_started:
                    relative_start = began - producer_started
                    if 0 <= relative_start < producer["compiler_seconds"]:
                        overlap.append({"producer": producer["crate"], "consumer": action["crate"],
                                        "codegen_overlap_seconds": producer["compiler_seconds"] - relative_start,
                                        "started_after_metadata": relative_start >= producer.get("metadata_seconds", 0)})
            del remaining[identifier]
    observed = [action for action in actions.values() if action.get("compiler_started_unix_nanos")]
    window = (max(action["compiler_started_unix_nanos"] / 1e9 + action["compiler_seconds"] for action in observed) -
              min(action["compiler_started_unix_nanos"] / 1e9 for action in observed)) if observed else None
    return {"compiler_actions": len(actions), "observed_compiler_window_seconds": window,
            "observed_dependency_overlaps": overlap,
            "compiler_only_paths_seconds": {"wait_for_complete_dependency": max(full.values()),
                                            "start_at_metadata": max(pipelined.values())},
            "limitations": "Paths ignore engine work and CPU limits, using durations observed during this Cargo capture. They are not predicted command wall times."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--batch", type=Path, help="use observed compiler timings from a batched replay report")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.batch:
        timings = {timing["id"]: timing for timing in json.loads(args.batch.read_text()).get("batch", [])}
        plan["actions"] = [action for action in plan["actions"] if action["id"] in timings]
        for action in plan["actions"]:
            timing = timings[action["id"]]
            action.update(compiler_seconds=timing["seconds"], metadata_seconds=timing.get("metadata_seconds", 0),
                          compiler_started_unix_nanos=timing["started_unix_nanos"])
            action["dependencies"] = [dep for dep in (action.get("dependencies") or []) if dep in timings]
    report = analyze(plan)
    contents = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(contents)
    else:
        print(contents, end="")


if __name__ == "__main__":
    main()
