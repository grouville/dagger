# Lazy Batch key index: measured complexity fix

2026-09-25. The final lazy index improves the real `Artifacts.Batch` grouping path **172.196 → 16.182 ms** at 10,000 unique keys (10.64×), in eight alternating pairs. One-key groups retain the same allocation count and bytes, and measure 1.551 → 1.560 µs. **No greetings-api listing/edit gain is claimed:** this phase is used by batched check/generator evaluation, not metadata-only listing.

## Change and correctness contract

For at most eight distinct keys per group, Batch continues using its ordered slice as a bounded membership scan. A ninth unique key creates a request-local membership set populated from the existing eight keys. Subsequent membership checks use the set while the slice preserves first-seen order. Repeated duplicates do not force promotion. The membership term changes from O(K²) comparisons to expected O(K) overall, with O(K) extra temporary memory only for larger groups. Group identity still includes workspace, path and parent dimensions; no new cache survives the invocation and no discovery invalidation changes. Other per-item cloning, identity serialization and schema replacement costs remain.

One aggregate `artifact.batch` wcprof operation identifies this phase. There are no per-key spans or new counters. Both baseline and candidate benchmark binaries contain identical wcprof instrumentation and run with profiling disabled.

## Final lazy-index benchmark

Eight before/after pairs alternate ordering, with each sample running the actual Batch function at all five sizes for 300 ms each. Each sample is a new test-binary process. GOMAXPROCS=8, Go 1.26.6, Intel Core i5-9300H. No engine workload or build overlaps this series. The two binaries have identical benchmark/test source; only baseline core/artifact_batch.go is replaced by an overlay with the old grouping algorithm and matching instrumentation. Values below are medians.

| Unique keys | Before | Lazy index | Speedup | Bytes/op before → after | Allocs/op before → after |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.001551 ms | 0.001560 ms | 0.99× | 1,977 → 1,977 | 13.0 → 13.0 |
| 10 | 0.015645 ms | 0.016317 ms | 0.96× | 20,407 → 21,391 | 128.0 → 132.0 |
| 100 | 0.170205 ms | 0.163241 ms | 1.04× | 203,552 → 209,857 | 1,214.0 → 1,222.0 |
| 1,000 | 2.991007 ms | 1.609029 ms | 1.86× | 2,021,788 → 2,130,232 | 12,025.0 → 12,044.0 |
| 10,000 | 172.196031 ms | 16.181570 ms | 10.64× | 20,662,260 → 21,532,768 | 120,062.5 → 120,127.5 |

At ten keys the promotion boundary still costs +0.673 µs / 4.3%, so this is not a win at every size. At 10,000 keys the added allocation volume is about 871 KB (+4.2%), in exchange for avoiding roughly 50 million string comparisons. Singleton groups have identical allocations; the median +9 ns difference does not establish a meaningful singleton slowdown.

## Correctness and scope

Focused `TestArtifact*|TestCollection*` tests pass on both binaries. Tests execute actual Batch using already-selected batch receivers, separating grouping from SDK schema registration/replacement. They verify ordered keys/results, parent/path isolation, identical keys in distinct parents, passthrough entries, empty-string keys, nonadjacent duplicates and unchanged source nodes/dimensions. Additional 7/8/9/16-unique-key cases put duplicates on both sides of promotion; the nine-key case explicitly repeats the key that creates the index. Repeated invocation verifies grouping state is not retained. The benchmark checks complete output key ordering outside its timed loop.

## Earlier eager-set prototype (separate series)

The earlier implementation allocated a set immediately. Its own matched series measured singleton 1.539 → 1.697 µs, +256 bytes and two allocations. Its 10,000-key median was 172.214 → 16.129 ms. Those results live in `../batch-index/`; they are not mixed into the final lazy-index medians above. The lazy revision removes the singleton allocation regression while retaining the large-collection complexity gain.

## Reproduction

Build both binaries with `go test -c ./core`, using `-overlay=before-overlay.json` only for baseline. Run the focused tests before benchmarking:

```sh
core-after.test -test.run='^(TestArtifact|TestCollection)' -test.count=1
python3 benchmark.py
```

Raw samples: `results.json`, `summary.json`, `NN-{before,after}.log`; checksums and base: `source-provenance.json`; focused test output: `test-{before,after}.log`; full source snapshots and the baseline overlay are included.
