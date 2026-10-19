# perf(dagql): avoid quadratic restored-cache indexing

A populated Go test collection cache exposed quadratic work when the engine restored its result index. Each equivalent digest received a separate copy of the same result set. The captured cache expanded 198,689 results into roughly 394 million associations; an idle heap profile attributed about 18 GB to that index.

Share each imported group's membership across its digests, and remove a result once per original group during pruning. Later digest-specific additions remain separate. This addresses both construction and removal of the shared representation in one PR.

This is part of the work to reduce Go test collection listing overhead on dagger/dagger.

### Performance

The complete-command check is `dagger check --module go --check test --list --all`; the import and prune fixtures below measure their named cache operations separately.

Fresh standalone measurements compare main `80699ac67a` with only this PR's production changes. Both binaries use identical import and prune fixtures.

| Operation | Main median | PR median | Allocated before → after | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Import 129 results | 7.31 ms | 4.66 ms | 2.41 → 1.58 MB | 4/4 |
| Import 2,049 results | 713.15 ms | 49.53 ms | 227.81 → 25.91 MB | 4/4 |
| Prune 2,049 roots | 844.75 ms | 12.75 ms | 3.95 → 3.95 MB | 4/4 |
| Prune 8,192 roots | 31.43 s | 45.59 ms | 16.01 → 16.01 MB | 4/4 |

Four alternating A/B and B/A pairs, Go 1.26.6, linux/amd64, GOMAXPROCS=8, one operation per sample. Import reopens the same persisted fixture shape with a warm filesystem cache. Setup and close are outside the measured operation. The slowest baseline prune, 67.16 s, remains included.

Import construction and storage become proportional to digests + results, instead of digests × results. Removal visits each original membership once and releases a group's digest aliases when it becomes empty.

These are cache-operation measurements, not complete Go listing timings. The earlier 5.12-second prune baseline already included the sharing change; it is not the main baseline above.

### Validation and tradeoffs

The complete standalone branch passes `go test -race -count=1 ./dagql` on main `80699ac67a`. Regressions check that class merges do not broaden old memberships, later exact additions stay local, and collection removes memberships across original groups. Import and prune fixtures verify retained result counts, no persistence reset, and the expected removals.

The change adds an in-memory group index under the existing graph lock. The persistence format and eviction policy are unchanged. Small groups still pay group bookkeeping; this fresh cohort measures wide groups and does not establish singleton-import overhead or a complete-listing gain. Candidate lookup keeps its existing compatibility checks and final result ordering.

[Clean source branch](https://github.com/grouville/dagger/tree/pr/go-collections-restored-index). [Standalone fixtures, raw samples and reproduction](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/restored-index).
