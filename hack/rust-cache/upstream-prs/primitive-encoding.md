Persisting a list currently constructs a result and copies the producer call for each item. For a bulk call with N input paths and N output hashes, those copies repeat the entire argument list N times.

Encode the four concrete built-in scalar arrays directly into the existing item envelopes. Keep the generic list encoder for all other values. This removes repeated call construction without changing the stored format or envelope version.

### Performance

Fresh measurements on `0cc85ff756`, based on main `717589c9cc`. Both sides use the same tests and benchmarks; the baseline restores only the production files to main.

Each case has N input paths and N returned strings, as in a bulk hash call. This exercises the repeated copying of the argument list.

| Items | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.74 µs | 978 ns | 3.13 KiB → 512 B | 33 → 11 |
| 10 | 41.92 µs | 5.68 µs | 65.06 KiB → 3.11 KiB | 456 → 47 |
| 128 | 3.13 ms | 67.58 µs | 6.61 MiB → 34.88 KiB | 36,001 → 519 |
| 512 | 46.88 ms | 280.81 µs | 102.09 MiB → 136.33 KiB | 537,460 → 2,055 |
| 1024 | 181.46 ms | 531.18 µs | 405.29 MiB → 272.40 KiB | 2,124,050 → 4,103 |

Six alternating A/B and B/A pairs in fresh processes, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. 150 ms per case, or at least one iteration for slower cases. These are component benchmarks, not complete Rust builds. They do not measure engine startup or remote cache transfer.

Every measured size was faster in all six pairs, including the one- and ten-item cases.

### Tradeoff and validation

The change extracts the existing generic loop into a helper and adds one scalar-array encoder with four callers. It adds no locks or shared state. Exact Go types determine eligibility; a custom scalar with the same schema name does not take this path.

The compatibility test compares the complete encoding with an independent wrapper that forces the generic path. It covers all four types, empty arrays, escaped and Unicode strings, exact 64-bit integers, negative zero, extreme floats, and NaN/infinity errors.

```sh
go test -race -count=1 ./dagql
```

To reproduce the component benchmark:

```sh
GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkPersistedPrimitiveArray' -benchmem -benchtime=150ms -count=6 ./dagql
```

Use identical benchmark sources on both sides and alternate execution order.
