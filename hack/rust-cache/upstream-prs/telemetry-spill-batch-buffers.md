# perf: reuse telemetry spill buffers for batch reads

Listing a large collection reads stored spans in batches. Each row currently allocates a raw frame before the decoder copies its fields into the returned row. The scanner's reader also misses its existing pool on this path.

Reuse one payload buffer per batch and return the reader when the read finishes, following the existing `readIDs` path. Decoded fields keep their own storage, so later reads cannot overwrite returned rows.

Six alternating before/after pairs, fresh processes, Go 1.26.6 and `GOMAXPROCS=8`:

| Rows per read | Time before → after | Allocated bytes before → after |
| --- | ---: | ---: |
| 1 | 10.26 → 1.96 µs | 68,775 → 3,116 |
| 512 | 619 → 424 µs | 1,614,839 → 830,824 |

File creation and fixture writes are outside the timer. Both cases improve in all six pairs. On sixteen complete edited Rust listings, the engine allocates a median **108 MB less per pair**, with lower allocations in **15/16 pairs**. Listings still take about 3.7 seconds; neither listing nor compilation latency improves consistently.

The full `engine/clientdb` race suite passes. The new test checks that returned rows survive buffer growth, later frames and another read, including nil and empty fields. A deliberately altered decoder that borrows the frame fails that test. All six retained native Rust histories remain fully reusable.

```sh
go test -race -count=1 ./engine/clientdb
go test -run '^$' -bench '^BenchmarkSpillFileReadSince$' -benchmem ./engine/clientdb
```

Four production lines are added, using the existing pool and no new lock. Scratch storage lasts for one read call; a large frame keeps that buffer until the call returns. The stored format and decoded field ownership remain compatible.

[Branch](https://github.com/grouville/dagger/tree/perf/telemetry-spill-batch-buffers) · [Measurements and validation](../NATIVE_TELEMETRY_READ_BUFFERS.md). No PR is open.
