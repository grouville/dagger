Searching test names through one native `Directory.search` per Go package is slower than the selected per-file workspace search on the real dagger/dagger repository. The candidate is rejected.

The experiment changes only the Go module. It imports the selected test files into a native Directory and searches their explicit basenames together, preserving filename order, match order, duplicate handling and overlay contents. Both versions pass the existing test collection checks and a new check that replaces a test in an already discovered package. The checks cover Unicode test names, overlays, ordering and selected execution.

`dagger check --module go --check test --list --all` runs against the same owned engine, CLI and upstream repository snapshot in both arms. Telemetry and ordinary GC stay enabled. Every invocation starts a fresh CLI and receives a fresh source edit. The linear restored-posting deletion path is common to both arms. One excluded initialization pair adds a real test; the measured pairs remove it.

| Measured pair | Per-file search | Directory search |
| --- | ---: | ---: |
| 1, candidate first | 43.35 s | 48.38 s |
| 2, original first | 43.04 s | 47.30 s |
| Median | 43.20 s | 47.84 s |

All six commands return the expected ordered rows and exit 0, including cleanup. The candidate is slower in both measured pairs. Median engine CPU rises from 229.12 to 241.28 seconds and allocations from 36.26 to 38.37 GB. This does not justify replacing the current discovery path. No engine API, collection granularity or cache identity is changed, and no PR is proposed.

[Candidate source, correctness output and complete measurements](experiments/go-package-search-recheck/).
