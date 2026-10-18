# Share encoded telemetry rows within an export

This is a controlled experiment, not a standalone upstream patch. The candidate is disabled after measurement.

The complete Go listing measures 39.49 → 35.87 seconds median, but improves only two of four pairs. A control run overlaps cache compaction. CPU and cumulative allocations fall in all four pairs; a reliable elapsed-time improvement is unproven. See [the assessment](../../NATIVE_TELEMETRY_SPAN_ROWS.md) for all timings and limitations.

`evidence.tar.gz` retains the effective source overlays, test and timing drivers, expected control failure, race checks, component cohorts, all complete-command attempts, exact output, diagnostic profiles and retained Rust-cache checks. The first admission timeout and closed-store component cohort are included. The final selected state keeps the candidate off. Diagnostic counters and profiling are off during timing; telemetry and ordinary GC remain on.

`MANIFEST.json` records every archived member's size and SHA-256. All 397 members were read back and verified. Compressed wcprof chunks and their reconstruction driver replace the redundant expanded event file. Source-context profiles copied from `collection-query-work-budget` describe the preceding investigation; the experiment's own capture is under `testdata/preflight/`.

Both timing arms use the same warm engine and volume, fresh CLI processes and fresh source edits. All measured commands return the same ordered 4,398 rows and exit successfully through cleanup. Cold startup is unmeasured. No new PR or upstream proposal is created by this study.
