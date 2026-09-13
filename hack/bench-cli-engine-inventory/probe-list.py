#!/usr/bin/env python3
"""Read-only alternating Docker inventory probe; not an e2e Rust benchmark."""
import hashlib
import json
import re
import statistics
import subprocess
import time

PREFIX = "dagger-engine-"
CUSTOM = "dagger-stream-close-order-6u5eynjb"
BASE = ["docker", "ps", "-a", "--format", "{{.Names}}"]
PATTERN = "^/?(" + re.escape(PREFIX) + ".*|" + re.escape(CUSTOM) + ")$"
COMMANDS = {"A": BASE, "B": BASE + ["--filter", "name=" + PATTERN]}


def invoke(args):
    start = time.perf_counter_ns()
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    if result.returncode:
        raise RuntimeError((args, result.returncode, result.stderr))
    names = tuple(line for line in result.stdout.splitlines() if line)
    selected = tuple(name for name in names if name.startswith(PREFIX) or name == CUSTOM)
    return {
        "elapsed_ms": elapsed,
        "returned_count": len(names),
        "selected": selected,
        "inventory_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
    }


initial = invoke(BASE)
assert CUSTOM in initial["selected"], "retained engine must be present"
samples = []
for pair in range(20):
    order = "AB" if pair % 2 == 0 else "BA"
    sample = {"pair": pair, "order": order}
    for side in order:
        sample[side] = invoke(COMMANDS[side])
        assert sample[side]["selected"] == initial["selected"], "selected inventory changed"
        if side == "A":
            assert sample[side]["inventory_sha256"] == initial["inventory_sha256"], "inventory changed"
        else:
            assert sample[side]["returned_count"] == len(initial["selected"])
    sample["saved_ms"] = sample["A"]["elapsed_ms"] - sample["B"]["elapsed_ms"]
    samples.append(sample)
final = invoke(BASE)
assert final["inventory_sha256"] == initial["inventory_sha256"], "inventory changed after probe"
print(json.dumps({
    "scope": "Read-only 20 alternating CLI inventory pairs, existing host inventory, no container mutation; not Rust end-to-end latency",
    "commands": COMMANDS,
    "initial": initial,
    "final": final,
    "samples": samples,
    "summary": {
        "A_median_ms": statistics.median(p["A"]["elapsed_ms"] for p in samples),
        "B_median_ms": statistics.median(p["B"]["elapsed_ms"] for p in samples),
        "saved_median_ms": statistics.median(p["saved_ms"] for p in samples),
        "saved_range_ms": [min(p["saved_ms"] for p in samples), max(p["saved_ms"] for p in samples)],
        "favorable": sum(p["saved_ms"] > 0 for p in samples),
    },
}, indent=2))
