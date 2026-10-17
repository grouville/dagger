Pruning a restored output class visits every digest for every result. Even when the digests share one imported membership map, removing R results with D aliases still does D × R work. Large groups occur in Go module discovery: one recorded class had 19,456 results and 19,457 digests.

Record each result's original imported groups. Remove its membership once per group, then clean up that group's aliases when its last result disappears. Keep later digest-specific entries and the original membership boundaries after class merges. The existing graph lock protects the index; ownership and eviction policy follow the existing path.

Complete DagQL metadata-prune passes on an imported fixture, three samples per arm:

| Roots removed | Before | After |
| --- | ---: | ---: |
| 513 | 16.22 ms | 3.42 ms |
| 2,049 | 274.84 ms | 10.72 ms |
| 8,192 | 5.122 s | 46.06 ms |

The largest pass allocates about 16 MB in both versions. Building the reverse index at restore adds 590 kB and about 3.5 ms for 4,096 independent results in this fixture.

The full DagQL race suite passes. Added tests cover removal across original imported groups and removal after a merge while preserving a later exact entry. Existing tests cover ownership, resource compatibility, expiry, persistence and compaction.

This extends the shared restored-postings proposal so removal also scales with the shared representation. Review it together with that proposal.

This improves cache-graph pruning. It does not establish a full Go collection-listing improvement: two complete-command pairs take 47.47 → 48.66 seconds, return the same 4,398 rows and exit 0. No metadata prune occurs in that cohort. A real listing workload exposed a separate 158-second metadata prune, but the portion attributable to this loop has not been measured directly. The diagnostic engine preserves its existing cache and all six native Rust histories across restart.

[Review branch](https://github.com/grouville/dagger/tree/perf/shared-restored-posting-removal). No PR is open.
