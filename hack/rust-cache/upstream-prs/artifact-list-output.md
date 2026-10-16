Large artifact listings can lose output. Each write to SpanStdio becomes a telemetry log record, and tabwriter emits separate writes for cells and padding. A burst can overflow the log queue before the exporter drains it.

Buffer the list output in 4 KiB chunks before writing to SpanStdio, and return flush errors to the caller. Reuse the table cell escaper rather than rebuilding it for every cell. The table, link and CLI formats keep the same output.

### Performance

Fresh measurements on `d1779ca777`, based on main `717589c9cc`. Both sides use the same tests and benchmarks; the baseline restores only the production files to main.

| Format / rows | Before median | Branch median | Allocated bytes before → branch | Allocations before → branch |
| --- | ---: | ---: | ---: | ---: |
| table / 1 | 15.33 µs | 6.89 µs | 27.16 KiB → 12.74 KiB | 82 → 49 |
| table / 10 | 109.12 µs | 21.14 µs | 239.21 KiB → 22.81 KiB | 505 → 184 |
| table / 1026 | 10.43 ms | 1.45 ms | 23.61 MiB → 1.13 MiB | 47,294 → 14,447 |
| link / 1 | 581 ns | 1.62 µs | 544 B → 4.60 KiB | 4 → 6 |
| link / 10 | 5.42 µs | 3.00 µs | 5.17 KiB → 5.24 KiB | 31 → 15 |
| link / 1026 | 535.05 µs | 132.99 µs | 529.35 KiB → 82.83 KiB | 3,079 → 1,059 |
| cli / 1 | 1.72 µs | 2.98 µs | 1.04 KiB → 5.10 KiB | 17 → 19 |
| cli / 10 | 15.52 µs | 13.47 µs | 10.15 KiB → 10.27 KiB | 153 → 137 |
| cli / 1026 | 1.55 ms | 1.15 ms | 1.02 MiB → 600.54 KiB | 15,394 → 13,375 |

Six alternating A/B and B/A pairs in fresh processes, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. 150 ms per case, or at least one iteration for slower cases. These are component benchmarks, not complete Rust builds. They do not measure engine startup or remote cache transfer.

Telemetry records per listing (before → branch): **table / 1026: 6,163 → 8**, **link / 1026: 1,026 → 15**, **cli / 1026: 1,026 → 16**. The benchmark uses a synchronous in-process exporter to measure formatting and record creation without network noise; the separate burst test uses a blocked batch exporter to reproduce output loss.

One-row link and CLI output are slower in all six pairs: about 1.0 µs and 1.3 µs respectively, with about 4 KiB and two extra allocations for the buffer. Larger cases and every table case are faster in all six pairs. The fixed buffer keeps the implementation simple; this small-case cost is the tradeoff for batching larger bursts.

### Tradeoff and validation

The buffer belongs to one listing and is flushed on return, including error returns. Output can be delayed until the buffer fills or rendering finishes; memory overhead is 4 KiB. This reduces queue pressure but does not make the telemetry queue unbounded or guarantee delivery for every possible burst.

The regression test blocks the exporter, writes 4,096 rows through the real telemetry writer, then verifies every row and its order in all three formats. It fails on main and passes with the fix. Closed-pipe tests cover errors during a write and during the final flush. Focused listing and formatting tests pass with the race detector.

```sh
go test -race -count=1 -run 'ArtifactList|ArtifactTable|ArtifactCLI' ./internal/cmd/dagger
```

To reproduce the component benchmark:

```sh
GOMAXPROCS=8 go test -run '^$' -bench '^BenchmarkArtifactListTelemetry' -benchmem -benchtime=150ms -count=6 ./internal/cmd/dagger
```

Use identical benchmark sources on both sides and alternate execution order.
