[Draft #14738](https://github.com/dagger/dagger/pull/14738) · [current source](https://github.com/grouville/dagger/tree/perf/review-span-child-index)

This is part of the work to make Go test collection listing faster. Listing the tests in dagger/dagger creates a wide trace: many spans share the same parent. The telemetry store currently scans all the existing children whenever it adds a new child. A diagnostic listing recorded more than two billion comparisons in that loop.

A new span ID cannot already be in a child list. Use the existing parent map to recognize that case and append directly. Keep the old duplicate check when an ID is reused across traces. Cause links have the same problem; their existing reverse index already tells us whether the edge exists.

The change adds no map or lock. It does less work under the existing lock and keeps the current duplicate, ordering and late-update behavior.

Building a fresh index on upstream main, with this change applied independently:

| Children sharing one parent | Main | This change |
| --- | ---: | ---: |
| 1,026 | 1.97 ms | 0.48 ms |
| 4,096 | 25.64 ms | 2.05 ms |

The equivalent 4,096-child cause-link case improves 26.36 → 2.16 ms. Six alternating pairs per case; all the larger cases improve, with unchanged allocation counts. The one-child controls establish no benefit: parent indexing takes 0.878 → 0.907 µs and cause-link indexing 0.908 → 0.909 µs.

An earlier complete Go listing comparison took 53.58 → 46.72 seconds across three successful pairs, returning the same 4,398 rows. One additional baseline command failed during cleanup and is retained in the results. Those measurements used an experimental engine with other changes held constant; they are not stock-main timings. The fresh small-command comparisons do not establish an end-to-end gain. The reason to propose this change is the quadratic work observed in a real listing, removed with the existing indexes and without extra tracking state.

`go test -race -count=1 ./engine/clientdb` passes on main and this change. The added test covers repeated snapshots, IDs reused across traces, late parent/link updates and edge order. To reproduce the index benchmark:

```sh
go test ./engine/clientdb -run '^$' -bench '^BenchmarkSpanLookupFanout$' -benchmem
```

[Earlier full-listing measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_GO_WIDE_TRACE_INDEX.md).

[Fresh raw measurements and checks](../experiments/standalone-go-collections/assessment/independent-followup-oct19/). The earlier source branch remains preserved separately.
