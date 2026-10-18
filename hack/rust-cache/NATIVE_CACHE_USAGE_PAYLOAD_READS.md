# Read only the payload fields needed by cache-usage sampling

The standalone change reduces capture of a loaded record with four snapshot references **541 → 198 ns**, and its revision check **332 → 17 ns**, faster in all four fixed component pairs. The revision check makes **five → zero allocations**. This is a small engine optimization; complete collection-listing impact is unmeasured, and it is not installed in the retained engine.

The [earlier listing tail](NATIVE_GO_QUERY_ATTRIBUTION.md) caught usage sampling in `loadPayloadState → cloneSnapshotRefLinks` while publication waited for the cache graph lock. On main, capture copies every payload field and deep-copies snapshot references. Unloaded records then receive another deep copy. Revision validation repeats the full payload copy just to compare the revision.

The patch reads the needed fields under the same payload read lock. A loaded value is retained as before; an unloaded record's references are deep-copied once. Validation checks graph membership before reading the revision. The existing graph lock still protects membership and size maps, which remain independent copies. Provider callbacks, ownership holds and resampling keep their existing paths. No new lock, cache format or eviction policy is introduced.

## Clean-main validation

[The isolated fork branch](https://github.com/grouville/dagger/tree/perf/cache-usage-payload-reads) is based on main `ff0b029a`, reverified before publication, with unchanged dependencies. The production change is confined to two functions in `dagql/cache_usage.go`. Existing usage/prune tests pass under the race detector before and after. One added regression mutates the row's reference, nested output path, size map and payload revision after capture; the captured values stay independent and the old sample becomes invalid. Existing callback, concurrent publication, cancellation, parent-chain and prune-planning tests cover those behaviors.

Four fixed pairs alternate order, each arm in a fresh Go test process, on Linux x86-64 with Go 1.26.6, eight scheduler threads and normal GC. The reference-bearing fixtures have four links with distinct two-element output paths and a previously measured size. Preparation is outside the benchmark loop. Separate column medians:

| Record | Operation | Before → after | Bytes/op | Allocations/op | Faster pairs |
| --- | --- | ---: | ---: | ---: | ---: |
| Loaded | Capture | 541.25 → 198.10 ns | 736 → 256 | 7 → 2 | 4/4 |
| Loaded | Validate | 331.75 → 17.19 ns | 480 → 0 | 5 → 0 | 4/4 |
| Unloaded | Capture | 859.00 → 527.95 ns | 1,216 → 736 | 12 → 7 | 4/4 |
| Unloaded | Validate | 333.65 → 17.15 ns | 480 → 0 | 5 → 0 | 4/4 |
| Scalar | Capture | 79.47 → 64.44 ns | 48 → 48 | 1 → 1 | 4/4 |
| Scalar | Validate | 29.19 → 17.20 ns | 0 → 0 | 0 → 0 | 4/4 |

The first fixed cohort used four duplicate ownership paths. Its results are preserved, but the committed benchmark uses distinct paths so its link set has unique ownership keys. The correction changes only the benchmark positions; production code, reference count, path lengths, size map, ownership regression and dependencies are unchanged. The corrected cohort above is the proposal's evidence. It is not a resampling of a negative timing result.

## Limits and next target

The maintenance-heavy profile establishes a real call site. It does not establish how often this sampling runs during an ordinary edited listing. The separate [compaction screen](NATIVE_CACHE_COMPACTION_DIGEST_SETS.md) shows why this distinction matters: faster complete-command observations need evidence that the changed code ran. This candidate stays separate from the selected engine, and no CLI-time saving is claimed.

The [review description](upstream-prs/cache-usage-payload-reads.md) is prepared for individual approval; no PR is opened. [Sources, both fixture cohorts, exact commands and race results](experiments/cache-usage-payload-reads/) are retained.
