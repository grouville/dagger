Selecting collection keys checks whether an ancestor already supplies the keys of each artifact. The current implementation compares every candidate with every entry, repeatedly rebuilding their dimension lists. A workspace with many independent collection fields pays quadratic cost even when none can hide another.

Build a local index of path components and ordered dimension identifiers, then look up each candidate's ancestors. Only ancestors that satisfy the selection filters enter the index. Keep the existing result order and exclusion behavior.

### Performance

Fresh measurements on `3fb5928e32`, based on main `717589c9cc`. Both sides use the same tests and benchmarks; the baseline restores only the production files to main.

| Collection fields (two artifact types each) | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4.60 µs | 4.40 µs | 3.96 KiB → 4.14 KiB | 71 → 64 |
| 10 | 174.89 µs | 36.74 µs | 106.34 KiB → 36.02 KiB | 3,140 → 535 |
| 100 | 15.07 ms | 361.88 µs | 7.90 MiB → 356.66 KiB | 283,310 → 5,221 |
| 1000 | 1.50 s | 3.75 ms | 765.66 MiB → 3.52 MiB | 28,033,013 → 52,032 |

Six alternating A/B and B/A pairs in fresh processes, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. 150 ms per case, or at least one iteration for slower cases. These are component benchmarks, not complete Rust builds. They do not measure engine startup or remote cache transfer.

The 10-, 100- and 1,000-field cases improved in all six pairs. One field has similar timing (five of six pairs faster) and allocates 184 additional bytes. There is no retained index to warm up: every measured call builds it again.

### Tradeoff and validation

The index is built for each call and is included in the benchmark. It adds maps and nodes; those allocations are the tradeoff for removing the all-pairs scan. It does not retain state between calls or add locks. Lookup cost depends on path and dimension depth; this is not a claim of constant cost for arbitrarily deep schemas.

Tests cover ancestors after descendants, literal field-path prefixes, different types at the same path and dimensions, ordered nested dimensions, required inner filters, and exclusions. Existing collection expansion, filtering, cancellation and persistence tests also pass with the race detector.

```sh
go test -race -count=1 -run '^(TestArtifact(Collection|DimensionKeys)|TestCollection|TestPersistedCollection)' ./core
```

To reproduce the component benchmark:

```sh
GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkArtifactDimensionKeys' -benchmem -benchtime=150ms -count=6 ./core
```

Use identical benchmark sources on both sides and alternate execution order.
