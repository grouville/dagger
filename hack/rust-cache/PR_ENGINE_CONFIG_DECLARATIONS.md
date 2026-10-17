Module-function cache lookup repeatedly reads and decodes the governing `dagger.toml`. A complete Go test listing on `dagger/dagger` loads the same 1.6 KB configuration 15,003 times, even when its contents do not change.

Reuse the derived Git-client declarations for identical current bytes. Keep every live read, nearest-config selection and error check. Entries contain immutable declaration strings and warnings; each caller receives its own slice and warning delivery. Concurrent misses share one decode outside the cache mutex. The cache holds at most 32 configurations and bypasses inputs above 64 KiB.

| Complete command | Before | After |
| --- | ---: | ---: |
| Go test collection listing | 45.51 s | 40.65 s |
| Cumulative engine allocation | 35.06 GB | 32.75 GB |

All four alternating pairs improve. Every command returns the same 4,398 ordered rows and exits successfully, including cleanup. Each invocation starts a fresh CLI and edits a used source file on the same warm engine. Telemetry and ordinary GC remain enabled. Initialization is retained separately. The candidate performs one decode for 15,003 lookups; result keys and compiled-result storage remain unchanged.

Misses have a cost: isolated distinct-content cases are about 1.5% slower. A combined benchmark shows a larger miss penalty; both are retained in the [measurement report](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_CONFIG_DECLARATION_REUSE.md).

The full workspace race suite passes on upstream code and the patch. Added checks cover fresh edits, nearer configurations, unreadable and invalid inputs, warnings for each caller, mutation and concurrent access. All six retained Rust histories preserve their compiler hits across restart and after the Go comparison.

[Review branch](https://github.com/grouville/dagger/tree/perf/reuse-git-client-declarations). No PR is open.
