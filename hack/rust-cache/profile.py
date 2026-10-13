#!/usr/bin/env python3
"""Capture one command's wall time and an isolated engine's wcprof recording."""

import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug-url", required=True, help="debug endpoint of an isolated profiler engine")
    parser.add_argument("--out", type=Path, required=True, help="capture directory outside the workspace")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("supply a command after --")
    output = args.out.resolve()
    if output.is_relative_to(Path.cwd().resolve()):
        parser.error("keep captures outside the workspace, for example under /tmp")
    output.mkdir(parents=True, exist_ok=True)
    base = args.debug_url.rstrip("/") + "/debug/wcprof/"

    def request(route, body=None):
        req = urllib.request.Request(base + route, data=body)
        return urllib.request.urlopen(req, timeout=60)

    with request("enabled") as response:
        state = json.load(response)
    if state["global_enabled"]:
        parser.error("wcprof is already recording on this engine; stop that recording before this capture")
    with request("enabled", b"on") as response:
        response.read()
    try:
        with request("dump") as response:
            # Discard the previous window without keeping a large dump in RAM.
            while response.read(1024 * 1024):
                pass
        started = time.monotonic()
        with (output / "command.log").open("w") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        wall = time.monotonic() - started
    finally:
        with request("enabled", b"off") as response:
            response.read()
        with request("dump") as response, (output / "profile.ndjson").open("wb") as dump:
            while chunk := response.read(1024 * 1024):
                dump.write(chunk)
    summary = {"command": command, "wall_seconds": wall, "exit_code": completed.returncode}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"command: {wall:.3f}s, exit {completed.returncode}; wcprof: {output / 'profile.ndjson'}")
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
