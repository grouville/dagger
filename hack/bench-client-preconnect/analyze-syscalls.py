#!/usr/bin/env python3
"""Offline, payload-free strace attribution; never launches measured commands.

The primary interval is successful execve entry -> earliest connect entry whose
observed return value is zero. Return-derived intervals are also retained. This
is an instrumented wall interval, not CPU time or an achievable speedup.
"""

import ast
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
LINE = re.compile(r"^(?:\[pid\s+(\d+)\]|(\d+))\s+(\d+\.\d+)\s+(.*)$")
RESUMED = re.compile(r"^<\.\.\. (\w+) resumed>(.*)$")
CALL = re.compile(r"^(\w+)\((.*)\)\s+=\s+(.+?)(?:\s+<([0-9.]+)>)?$")
CSTRING = r'"(?:\\.|[^"\\])*"'
EXEC_ARGS = re.compile(r"^\s*(" + CSTRING + r")\s*,\s*(\[.*\])\s*,\s*.*$")
SOCKET = re.compile(r'\bsun_path=("(?:\\.|[^"\\])*")')
SOCKETS = {"/var/run/docker.sock", "/run/docker.sock"}
SYSCALLS = {"execve", "connect", "clone", "clone3", "fork", "vfork"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ns(value):
    return int(Decimal(value) * 1_000_000_000)


def event_ref(event):
    return {key: event.get(key) for key in (
        "tid", "syscall", "start_ns", "return_derived_ns", "duration_ns",
        "line", "resume_line", "resume_observed_ns", "result",
    )}


def exec_args(event):
    match = EXEC_ARGS.match(event["args"])
    if not match:
        return None, None, "unrecognized execve argument structure"
    try:
        executable = ast.literal_eval(match[1])
    except (SyntaxError, ValueError) as error:
        return None, None, "unparsed executable: " + type(error).__name__
    try:
        argv = ast.literal_eval(match[2])
    except (SyntaxError, ValueError) as error:
        return executable, None, "unparsed/truncated execve argv: " + type(error).__name__
    if not isinstance(executable, str) or not isinstance(argv, list) or not all(
        isinstance(arg, str) for arg in argv
    ):
        return executable, None, "non-string or truncated execve argv"
    return executable, argv, None


def classify(executable, argv):
    if not isinstance(executable, str) or Path(executable).name != "docker":
        return "not-docker"
    if argv is None:
        return "docker-unparsed"
    if len(argv) > 1 and argv[1] == "version":
        return "docker-version"
    if len(argv) > 1 and argv[1] == "exec":
        if argv[-2:] == ["buildctl", "dial-stdio"]:
            return "docker-exec-buildctl-dial-stdio"
        return "docker-exec-other"
    # Do not infer subcommands through arbitrary global option/value pairs.
    return "docker-other"


def parse_trace(path):
    events, issues, process_messages = [], [], []
    unsupported_exec_transfer_tids = set()
    pending = {}
    line_count = 0
    with path.open(encoding="utf-8", errors="strict") as stream:
        for line_count, raw in enumerate(stream, 1):
            raw = raw.rstrip("\n")
            match = LINE.match(raw)
            if not match:
                issues.append({"kind": "unmatched_line", "line": line_count, "raw": raw})
                continue
            tid, timestamp, body = int(match[1] or match[2]), ns(match[3]), match[4]
            if body.startswith("+++"):
                process_messages.append({"tid": tid, "time_ns": timestamp, "line": line_count, "text": body})
                if "superseded" in body:
                    unsupported_exec_transfer_tids.add(tid)
                    transferred = re.search(r"\bpid (\d+)", body)
                    if transferred:
                        unsupported_exec_transfer_tids.add(int(transferred[1]))
                    issues.append({"kind": "unsupported_exec_pid_transfer", "line": line_count, "raw": raw})
                continue
            resumed = RESUMED.match(body)
            event = {"tid": tid, "start_ns": timestamp, "line": line_count}
            if resumed:
                old = pending.pop(tid, None)
                if old is None or old["syscall"] != resumed[1]:
                    issues.append({"kind": "unmatched_resume", "line": line_count, "raw": raw, "pending": old})
                    continue
                event = old
                event.update(resume_line=line_count, resume_observed_ns=timestamp)
                body = event.pop("prefix") + resumed[2]
            elif body.endswith("<unfinished ...>"):
                start = re.match(r"^(\w+)\(", body)
                if not start:
                    issues.append({"kind": "unparsed_unfinished", "line": line_count, "raw": raw})
                    continue
                if tid in pending:
                    issues.append({"kind": "replaced_pending", "line": line_count, "pending": pending[tid]})
                event.update(syscall=start[1], prefix=body.removesuffix("<unfinished ...>").rstrip())
                pending[tid] = event
                continue
            call = CALL.match(body)
            if not call or call[1] not in SYSCALLS:
                issues.append({"kind": "unparsed_record", "line": line_count, "raw": raw, "assembled": body})
                continue
            result_match = re.match(r"^(-?\d+)(?:\s|$)", call[3])
            duration = ns(call[4]) if call[4] is not None else None
            event.update(syscall=call[1], args=call[2], result=call[3],
                         return_value=int(result_match[1]) if result_match else None,
                         duration_ns=duration,
                         return_derived_ns=event["start_ns"] + duration if duration is not None else None)
            events.append(event)
    for unfinished in pending.values():
        issues.append({"kind": "unfinished_at_eof", "pending": unfinished})

    # Resolve the complete clone graph after parsing: a child may execute or
    # connect before its parent's unfinished clone return appears in the log.
    births = defaultdict(list)
    for event in events:
        if event["syscall"] in {"clone", "clone3", "fork", "vfork"} and (event["return_value"] or 0) > 0:
            births[event["return_value"]].append(event)
    execs = sorted((event for event in events if event["syscall"] == "execve" and event["return_value"] == 0),
                   key=lambda event: (event["start_ns"], event["line"]))
    traced_root = execs[0]["tid"] if execs and execs[0]["tid"] not in births else None
    leaders = {}

    def leader(tid, visiting=None):
        if tid in leaders:
            return leaders[tid]
        if tid in unsupported_exec_transfer_tids:
            leaders[tid] = None
            return None
        visiting = set() if visiting is None else visiting
        if tid in visiting:
            leaders[tid] = None
            issues.append({"kind": "clone_cycle", "tid": tid})
            return None
        visiting.add(tid)
        born = births.get(tid, [])
        if len(born) > 1:
            # PID/TID reuse needs generation-aware analysis; do not silently
            # combine different lifetimes into one Docker process.
            result = None
            issues.append({"kind": "ambiguous_tid_birth_or_reuse", "tid": tid,
                           "births": [event_ref(item) for item in born]})
        elif born:
            birth = born[0]
            if re.search(r"\bCLONE_THREAD\b", birth["args"]):
                result = leader(birth["tid"], visiting)
            else:
                result = tid
        elif tid == traced_root:
            result = tid
        else:
            result = None
        visiting.remove(tid)
        leaders[tid] = result
        return result

    tids = {event["tid"] for event in events} | set(births)
    for tid in sorted(tids):
        leader(tid)
    by_process = defaultdict(list)
    for event in execs:
        by_process[leader(event["tid"])].append(event)

    socket_connects = []
    for event in events:
        if event["syscall"] != "connect":
            continue
        socket = SOCKET.search(event["args"])
        if not socket:
            continue
        try:
            socket_path = ast.literal_eval(socket[1])
        except (SyntaxError, ValueError):
            issues.append({"kind": "unparsed_socket_path", **event_ref(event), "args": event["args"]})
            continue
        if socket_path in SOCKETS:
            socket_connects.append(dict(event, socket_path=socket_path, process_leader=leader(event["tid"])))

    rows, exec_records = [], []
    associated_connect_lines = set()
    for event in sorted((item for item in events if item["syscall"] == "execve"), key=lambda item: item["start_ns"]):
        executable, argv, parse_error = exec_args(event)
        record = dict(event_ref(event), executable=executable, argv=argv,
                      argv_classification=classify(executable, argv),
                      process_leader=leader(event["tid"]), parse_error=parse_error)
        exec_records.append(record)
        if parse_error:
            issues.append({"kind": "execve_arguments", **event_ref(event), "error": parse_error, "args": event["args"]})
        if record["argv_classification"] == "not-docker" or event["return_value"] != 0:
            continue
        pid = record["process_leader"]
        row = dict(record, pid=pid, execve_timestamp_ns=event["start_ns"],
                   first_successful_docker_socket_connect=None, launch_to_connect_ms=None,
                   launch_to_connect_return_ms=None, status="unmatched", socket_attempts=[])
        if pid is None or event["tid"] != pid:
            row["unmatched_reason"] = "unresolved process leader or unsupported non-leader execve"
            rows.append(row)
            continue
        later_execs = [other["start_ns"] for other in by_process[pid] if other["start_ns"] > event["start_ns"]]
        next_exec = min(later_execs) if later_execs else None
        attempts = [item for item in socket_connects if item["process_leader"] == pid
                    and item["start_ns"] >= event["start_ns"]
                    and (next_exec is None or item["start_ns"] < next_exec)]
        attempts.sort(key=lambda item: (item["start_ns"], item["line"]))
        row["socket_attempts"] = [dict(event_ref(item), socket_path=item["socket_path"]) for item in attempts]
        associated_connect_lines.update(item["line"] for item in attempts)
        successful = [item for item in attempts if item["return_value"] == 0]
        if successful:
            first = successful[0]
            row["first_successful_docker_socket_connect"] = dict(event_ref(first), socket_path=first["socket_path"])
            row["launch_to_connect_ms"] = (first["start_ns"] - event["start_ns"]) / 1_000_000
            if first["return_derived_ns"] is not None:
                row["launch_to_connect_return_ms"] = (first["return_derived_ns"] - event["start_ns"]) / 1_000_000
            row["status"] = "matched"
        else:
            row["unmatched_reason"] = "no observed successful Docker socket connect in this executable lifetime"
        rows.append(row)
    failed_syscalls = [dict(event_ref(event), args=event["args"]) for event in events
                       if event["return_value"] is None or event["return_value"] < 0]
    return {
        "path": str(path), "sha256": sha(path), "bytes": path.stat().st_size,
        "lines": line_count, "completed_syscall_counts": dict(Counter(event["syscall"] for event in events)),
        "traced_root_tid": traced_root, "tid_to_process_leader": {str(tid): leaders[tid] for tid in sorted(leaders)},
        "thread_birth_count": sum(bool(re.search(r"\bCLONE_THREAD\b", event["args"]))
                                  for events_for_tid in births.values() for event in events_for_tid),
        "docker_processes": rows, "execve_records": exec_records,
        "unassociated_docker_socket_connects": [dict(event_ref(event), socket_path=event["socket_path"],
                                                     process_leader=event["process_leader"])
                                                for event in socket_connects if event["line"] not in associated_connect_lines],
        "failed_or_unknown_syscalls": failed_syscalls, "parser_issues": issues,
        "process_messages": process_messages,
    }


def main():
    if sys.argv[1:]:
        raise SystemExit("No arguments: analyze only this capture's declared syscall inputs.")
    output = ROOT / "syscall-analysis.json"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    capture_path = ROOT / "capture.json"
    capture = json.loads(capture_path.read_text())
    if capture.get("status") != "passed" or capture.get("exit_code") != 0:
        raise SystemExit("Capture has not completed successfully; no analysis written.")
    run_root = Path(capture["root"]).resolve(strict=True)
    diagnostic_path = run_root / "boundary-diagnostics.json"
    diagnostics = json.loads(diagnostic_path.read_text())
    if diagnostics.get("status") != "passed":
        raise SystemExit("Boundary diagnostics have not completed successfully.")
    runs = diagnostics["runs"]
    selected = [run for run in runs if run.get("variant") == "syscalls"]
    if len(selected) != 9 or len({run["label"] for run in selected}) != 9:
        raise SystemExit("Expected exactly nine distinctly labelled syscall runs.")
    paths = [Path(run["syscall_trace"]).resolve(strict=True) for run in selected]
    if len(set(paths)) != 9 or any(path.parent != run_root for path in paths):
        raise SystemExit("Trace paths must be nine distinct files in the declared run root.")
    reports = []
    for run, path in zip(selected, paths):
        reports.append({"label": run["label"], "scenario": run["scenario"], "sample": run["sample"],
                        "profiled": run.get("profiled"), "process_ms_with_strace": run["milliseconds"],
                        "trace": parse_trace(path)})
    source_paths = [Path(__file__).resolve(), ROOT / "capture.py", ROOT / "run-diagnostic.py"]
    report = {
        "schema_version": 1, "scope": "offline Docker process-to-socket attribution; not a performance comparison",
        "interval_definition": "successful execve syscall entry -> earliest connect syscall entry with observed return value 0",
        "return_timestamp_definition": "syscall entry plus strace -T duration; resumed-record timestamp retained separately",
        "source_hashes": {str(path): sha(path) for path in source_paths},
        "input_hashes": {str(path): sha(path) for path in (capture_path, diagnostic_path)},
        "recorded_capture_source_pins_not_revalidated": capture.get("source_hashes", {}),
        "capture_root": str(run_root), "capture_status": capture["status"],
        "diagnostic_runs": runs, "syscall_runs": reports,
        "docker_process_counts_by_classification": dict(Counter(
            row["argv_classification"] for run in reports for row in run["trace"]["docker_processes"])),
        "matched_processes": sum(row["status"] == "matched" for run in reports for row in run["trace"]["docker_processes"]),
        "parser_issue_count": sum(len(run["trace"]["parser_issues"]) for run in reports),
        "limits": [
            "strace perturbs timing; both syscall and paired plain runs also enable wcprof. These are not headline timings.",
            "The interval includes wall-clock scheduling, loader/runtime/client setup and instrumentation, not pure CPU.",
            "A successful Unix socket connect is not Docker API, exec, buildctl, HTTP/2 or Dagger request readiness.",
            "No claim that this whole interval is removable; overlapping process intervals must not be added as end-to-end savings.",
            "Identical docker exec argv does not identify foreground versus telemetry versus attachables versus BuildKit ownership.",
            "Only completed return-value-0 connects to the two exact Docker socket paths count. EINPROGRESS is not assumed successful.",
            "Arguments are the bounded strace representation; truncated/unparsed argv and unmatched/resumed errors are retained, not guessed.",
            "CLONE_THREAD relations are resolved after assembling unfinished/resumed records; ambiguous PID reuse and non-leader exec are not assigned.",
            "Capture binary/source pins are copied as provenance; this parser rehashes only its own sources and metadata/syscall inputs, not binaries or OTLP.",
        ],
    }
    # Exclusive creation is the final guard against concurrent accidental overwrite.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(output), "sha256": sha(output), "syscall_runs": len(reports),
                      "matched_processes": report["matched_processes"],
                      "parser_issue_count": report["parser_issue_count"]}, indent=2))


if __name__ == "__main__":
    main()
