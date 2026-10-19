# perf(dagql): skip disk-usage sampling for empty values

Disk-prune preparation builds usage records and takes temporary references for every cached result, including scalars and metadata with no disk usage. Large Go collection listings accumulate many such values, extending preparation under the graph lock.

Skip values with no usage provider, snapshot links or previous measurements to clear. Finalization still rechecks omitted values: an empty value replaced by a provider must be sampled before pruning. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Measurement | Before | After |
| --- | ---: | ---: |
| 200,000-result usage snapshot | 590 ms / 159 MB | 335 ms / 91 MB |
| Preparation on the retained engine cache | 5.12 s / 1.06 GB | 3.22 s / 495 MB |
| Complete Go test listing | 49.10 s | 45.40 s |

The fixture improves in all three alternating pairs. Real-cache preparation improves in all four pairs, preserving the same 854,567 results and measured usage without eviction. A provider-only control has unchanged allocation and no observed slowdown.

Complete listing improves **7.5%**, in all four pairs. Each command starts a fresh CLI, edits source on the same warm experimental engine, returns the same 4,398 ordered rows, and includes telemetry and successful cleanup. Background pruning affects the magnitude; this is not a cold-start or stock-main comparison.

### Validation and tradeoffs

The full DagQL race suite passes. Added tests cover empty values becoming providers and clearing old usage after providers become empty. Existing tests cover callback lifetime, cancellation, shared snapshots and pruning decisions. Six Rust compilation histories retain their action hits across restart and after the listing cohort.

The change is confined to usage sampling, without a new index or lock. Provider validation and eviction policy retain their existing behavior.

[Source](https://github.com/grouville/dagger/tree/perf/skip-empty-usage-sampling). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_CACHE_USAGE_PROVIDER_SAMPLING.md).
