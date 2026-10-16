Bulk calls can take a list of paths and return a list of hashes. The cache walks every returned item looking for snapshot ownership and cleanup hooks. Constructing each item copies the producer call, including the whole input list, so N inputs and N outputs cause quadratic work.

Skip those item walks for the four concrete built-in scalar arrays: String, Int, Float and Boolean. These values cannot own snapshots, part hosts or cleanup hooks. Lists of objects and custom scalars still use the existing walk, even when their schema type is named String. The authoritative list declaration is still checked before the shortcut.

### Performance

Fresh measurements on `8a21f6cfe0`, based on main `717589c9cc`. Both sides use the same tests and benchmarks; the baseline restores only the production files to main.

Each case has N input paths and N returned strings, as in a bulk hash call. This exercises the repeated copying of the argument list.

| Items / operation | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| 1 / snapshot_links | 2.46 µs | 869 ns | 4.09 KiB → 1.51 KiB | 34 → 12 |
| 1 / part_hosts | 1.98 µs | 236 ns | 2.73 KiB → 32 B | 26 → 2 |
| 10 / snapshot_links | 33.56 µs | 1.64 µs | 64.28 KiB → 3.27 KiB | 421 → 21 |
| 10 / part_hosts | 34.88 µs | 236 ns | 62.14 KiB → 32 B | 422 → 2 |
| 128 / snapshot_links | 3.10 ms | 11.98 µs | 6.58 MiB → 26.44 KiB | 35,467 → 139 |
| 128 / part_hosts | 3.02 ms | 239 ns | 6.57 MiB → 32 B | 35,586 → 2 |
| 512 / snapshot_links | 46.08 ms | 44.12 µs | 101.95 MiB → 102.06 KiB | 535,051 → 523 |
| 512 / part_hosts | 45.70 ms | 239 ns | 101.90 MiB → 32 B | 535,554 → 2 |
| 1024 / snapshot_links | 181.70 ms | 88.34 µs | 404.89 MiB → 202.56 KiB | 2,118,668 → 1,035 |
| 1024 / part_hosts | 181.11 ms | 239 ns | 404.80 MiB → 32 B | 2,119,684 → 2 |

Six alternating A/B and B/A pairs in fresh processes, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. 150 ms per case, or at least one iteration for slower cases. These are component benchmarks, not complete Rust builds. They do not measure engine startup or remote cache transfer.

Every measured size was faster in all six pairs, including the one- and ten-item cases.

### Tradeoff and validation

The production change is a four-type switch in the existing ownership walker, plus renaming that walker to describe its purpose. It adds no shared state or locks. The main risk is accidentally skipping an owning value; the custom String-named scalar test verifies snapshot links, part-host attachment and exactly one cleanup call. Another test keeps malformed list declarations rejected.

```sh
go test -race -count=1 ./dagql
```

To reproduce the component benchmark:

```sh
GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkPrimitiveArrayOwners' -benchmem -benchtime=150ms -count=6 ./dagql
```

Use identical benchmark sources on both sides and alternate execution order.
