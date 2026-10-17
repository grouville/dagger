Disk-prune preparation builds usage records and takes temporary references for every cached result, including scalars and metadata with no disk usage. On a large cache, this holds the graph lock long enough to delay normal queries.

Skip values with no usage provider, snapshot links or old measurements to clear. Finalization still rechecks omitted values, so a value replaced by a provider must be sampled before pruning. Providers keep the existing validation, ownership and callback paths. The implementation adds 19 lines and removes two in one file, with no new index or lock.

| Measurement | Before | After |
| --- | ---: | ---: |
| Existing 200,000-result disk snapshot | 590 ms / 159 MB | 335 ms / 91 MB |
| Full preparation on the retained engine cache | 5.12 s / 1.06 GB | 3.22 s / 495 MB |
| Complete Go test listing on dagger/dagger | 49.10 s | 45.40 s |

The component fixture improves in all three alternating pairs. Real-cache preparation improves in all four pairs, preserving the same 854,567 results and measured disk usage without eviction. A provider-only fixture has unchanged allocation and no observed slowdown across three pairs.

Full listing improves in all four measured pairs. Each invocation starts a fresh CLI and edits a used source file on the same warm engine. All commands return the expected ordered rows and exit successfully, including cleanup. Telemetry and ordinary GC stay enabled. Background pruning can affect the magnitude, and listing remains too slow.

The full DagQL race suite passes. Two added checks cover an empty value becoming a provider and clearing old measurements after a provider becomes empty. Existing checks cover callback lifetime, cancellation, shared snapshots and pruning decisions. All six retained Rust histories preserve their expected action hits before restart, on their first calls afterward and after the Go cohort.

[Review branch](https://github.com/grouville/dagger/tree/perf/skip-empty-usage-sampling). No PR is open.
