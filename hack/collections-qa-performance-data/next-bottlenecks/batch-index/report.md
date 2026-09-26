# Batch key membership: measured complexity fix

2026-09-25. The real `Artifacts.Batch` grouping path improves **172.21 → 16.13 ms** at 10,000 unique keys (10.68×), in eight alternating pairs. This is a scaling improvement for batched check/generator evaluation, **not a measured greetings-api listing or edit improvement**. Metadata-only `check -l --all` does not traverse this Batch phase.

## Change and cache contract

Each request-local group now has a membership set in addition to its existing ordered key slice. Previously every unique key scanned all earlier keys, requiring K(K−1)/2 comparisons for K unique keys in one group. The membership term is now expected O(K) overall, with O(K) additional temporary memory. Existing first-seen order and group identity (workspace, artifact path and parent dimensions) are unchanged. No cache survives the Batch invocation; no workspace reads, invalidation or execution semantics change. Other per-item cloning, identity serialization and schema replacement costs remain.

One aggregate `artifact.batch` wcprof operation separates batching from the larger evaluation-items phase. It uses the existing recorder and is nil-safe when profiling is disabled. No per-key spans or new counter system were added. Both benchmark binaries include this identical instrumentation, with profiling disabled.

## Full Batch microbenchmark

Eight pairs alternate before/after order. Each sample runs all five sizes for 300 ms each, with a new test-binary process, GOMAXPROCS=8, Go 1.26.6 on an Intel Core i5-9300H. Both binaries compile the same test source. The baseline overlay uses the exact HEAD Batch body plus identical wcprof instrumentation. No engine, other benchmark or build overlaps the measured series. Times are medians.

| Unique keys | Before | After | Speedup | Bytes/op before → after | Allocs/op before → after |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.001538 ms | 0.001697 ms | 0.91× | 1,977 → 2,233 | 13 → 15 |
| 10 | 0.015797 ms | 0.016816 ms | 0.94× | 20,407 → 21,119 | 128 → 133 |
| 100 | 0.170733 ms | 0.162280 ms | 1.05× | 203,554 → 210,510 | 1,214 → 1,225 |
| 1,000 | 3.056967 ms | 1.598548 ms | 1.91× | 2,021,826 → 2,130,890 | 12,025 → 12,047 |
| 10,000 | 172.214435 ms | 16.128624 ms | 10.68× | 20,662,212 → 21,533,639 | 120,063 → 120,133 |

The simple set trades a small-group regression for predictable scaling: +159 ns / 10.3% for one key and +1.02 µs / 6.4% for ten keys. At 10,000 keys it adds approximately 871 KB (+4.2%) to the roughly 20.7 MB already allocated by the complete grouping path. A bounded small-group scan with lazy set creation could avoid the extra allocation for tiny groups; that alternative has not been implemented or measured here.

## Correctness

`TestArtifact*|TestCollection*` passes on both baseline and candidate. The new focused test invokes actual Batch on already-selected batch receivers (schema replacement is deliberately outside this fixture). It asserts first-seen result/key order; separated parent dimensions and paths; interleaved/nonadjacent duplicate keys including the empty string; identical key strings under different parents; passthrough artifacts; repeated calls; and unchanged source node/key/dimension values. The benchmark checks the full output key order after each timed loop.

Both binaries were built using `go test -c ./core`, with `-overlay=before-overlay.json` only for the baseline. Focused test command:

```sh
core-after.test -test.run='^(TestArtifact|TestCollection)' -test.count=1
```

Raw data: `results.json`, `summary.json`, per-run `.log` files; repeat driver: `benchmark.py`; source/binary checksums: `source-provenance.json`; focused output: `test-{before,after}.log`.
