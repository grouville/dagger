# Native workspace search for Go test names

The full edited listing measures **36.43 → 34.99 seconds median**, faster in four of four pairs, with correct ordered output and successful cleanup. Cumulative allocation rises **29.11 → 29.55 GB**, and CLI peak RSS rises **653 → 756 MiB**. The candidate remains an isolated prototype, requiring the separate host-overlay engine fix. See [the assessment](../../NATIVE_GO_WORKSPACE_SEARCH.md).

`evidence.tar.gz` contains the exact module sources, original overlay failure, passing collection and retained-package checks, all ten unprofiled commands, separate wcprof captures, critical-path reports, fork revisions and final restored state. The excluded initialization adds a test and returns 4,399 rows; measured pairs remove it and return 4,398.

`MANIFEST.json` records sizes and SHA-256 hashes for all **106 verified archive members**. Expanded wcprof files are omitted in favor of their archived compressed chunks and reconstruction driver. Profiling and diagnostic counters are off during timing; telemetry and ordinary GC remain on. Cold startup is unmeasured.

[The prototype branch](https://github.com/grouville/go/tree/experiment/workspace-package-test-search) is pushed for tracking. Its engine dependency and resource tradeoffs remain explicit; it is not an additional ready Go-module proposal. No PR is open. The original module stays selected by default, and every retained Rust compilation remains reusable.
