# perf(dagql): share restored cache membership during import and pruning

A populated Go test collection cache exposed quadratic work when the engine restored its result index. Each equivalent digest received a separate copy of the same result set. The captured cache expanded 198,689 results into roughly 394 million associations; an idle heap profile attributed about 18 GB to that index.

Share each imported group's membership across its digests, and remove a result once per original group during pruning. Later digest-specific additions remain separate. This addresses both construction and removal of the shared representation in one PR.

This is part of the work to reduce Go test collection listing overhead on dagger/dagger.

### Performance

The complete-command check is `dagger check --module go --check test --list --all`; the import and prune fixtures below measure their named cache operations separately.

Cache import, reopening the same persisted fixture with a warm filesystem cache:

| Restored results | Before | After | Allocated before → after |
| --- | ---: | ---: | ---: |
| 129 | 7.62 ms | 5.39 ms | 2.41 → 1.57 MB |
| 513 | 44.46 ms | 13.16 ms | 19.05 → 6.25 MB |
| 2,049 | 690.37 ms | 45.11 ms | 227.81 → 25.61 MB |

Import construction and storage become proportional to digests + results, instead of digests × results. Three alternating pairs; shutdown is outside the interval.

The removal follow-up reduces a complete 8,192-root fixture prune from **5.122 s to 46.06 ms**, across three samples per arm. Its reverse index costs an additional 590 kB and about 3.5 ms when restoring 4,096 independent results.

These are cache-operation benchmarks. A separate full-listing cohort takes **47.47 → 48.66 s**, with no metadata prune during those commands. It establishes no listing latency gain.

### Validation and tradeoffs

The full DagQL race suite passes. Regressions check that class merges do not broaden old memberships, later exact additions stay local, and collection removes memberships across original groups. The existing cache and six Rust compilation histories survive a graceful restart.

The change adds an in-memory group index under the existing graph lock. It changes neither the persistence format nor eviction policy. The benefit is bounded restore memory and removal work; these measurements do not establish a shorter lock hold time for every workload.

[Source](https://github.com/grouville/dagger/tree/perf/shared-restored-posting-removal). [Import measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_SHARED_RESTORED_POSTINGS.md) and [removal measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_RESTORED_POSTING_REMOVAL.md).
