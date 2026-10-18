# Rejected package test snapshot prototype

The complete real-repository test-file-edited listing regresses 18.60 → 55.76 seconds, slower in all four balanced pairs. All rows and command exits are correct. No PR or production change is proposed.

`evidence.tar.xz` contains the exact source diff, before/after source, three focused checks, all ten complete-command attempts, restoration and pressure records, and a lossless wcprof capture with attribution. `MANIFEST.json` verifies every member and the archive. The engine/CLI source and initial module branch are inherited from `../native-go-test-discovery/` and its referenced archives; binary identities are captured in the metadata.

Extract to a temporary directory. Rebuild the combined trace with `python3 assemble-traces.py capture-test-edit`; the script verifies the exact byte length and SHA-256. `python3 analyze.py capture-test-edit` uses the existing `/tmp/rust-cache-wcprof-report` tool. Capture and timing drivers refer to the recorded local worktrees and existing persistent engine; use the source identities and preceding experiment to reproduce that development stack. They must run sequentially with no other benchmark or profiler. These are local diagnostic drivers, not a standalone stock-main benchmark.

The candidate source starts at Go commit `6b9173a88d8c2c97cee0c9ee59735b0236275f9b`; apply `module.patch` or copy `after-go.dang`. `measure-test-edits.py` performs one initialization pair followed by four alternating measured pairs, mutates a real test file in every arm, checks exact rows and restores source/configuration/flags. `capture.py` records a separate diagnostic; it is not a latency comparison. Snapshot managers, caches, telemetry and ordinary GC are preserved.
