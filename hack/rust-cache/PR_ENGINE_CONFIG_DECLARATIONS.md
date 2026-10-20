[Draft PR #14741](https://github.com/dagger/dagger/pull/14741)

This is part of the work to make Go test collection listing faster. While listing the tests in `dagger/dagger`, the engine decoded the same 1.6 kB `dagger.toml` 15,003 times to check which Git clients a module may use. This happens before looking up the module function's cached result, even when the configuration declares no Git clients.

Reuse those declarations when the current configuration bytes are identical. Every lookup still reads the file and selects the nearest configuration, so edits, newly added files and read errors take effect immediately. The cache holds at most 32 configurations, skips files over 64 KiB, and uses the existing LRU library. Concurrent requests share one parse; parsing and warning delivery happen outside the cache lock. Each caller receives its own declaration slice and warnings.

The median complete listing measured 45.51 s → 40.65 s (4.21 s median paired saving), with engine allocations falling from 35.06 GB to 32.75 GB. All four alternating pairs improved and returned the same 4,398 ordered rows, including successful command cleanup. Each command started a fresh CLI and edited a source file on a warm engine, with normal telemetry and GC.

That end-to-end comparison used our experimental engine, with the other changes held constant and only declaration reuse toggled. It is evidence for this workload, not a measurement of this patch alone on today's main. The patch here is independent and based on `ce6dc9f9403b52067f5831149eab4871f857185d`; the configuration-loading code has not changed since that comparison.

Fresh benchmarks against that main commit use the same real configuration, four alternating pairs per case, and 5,000 lookups per process:

| Lookup | Main | This change | Allocations per lookup |
| --- | ---: | ---: | ---: |
| Same configuration | 324.93 µs | 3.99 µs | 2,818 → 3 |
| Same configuration, concurrent callers | 139.61 µs | 1.18 µs | 2,818 → 3 |
| Different configuration on every lookup | 335.41 µs | 351.06 µs | 2,823 → 2,826 |

The cost is a bounded shared cache and about 4.7% more time when every lookup sees new content. That case gets no reuse benefit. The concurrent row reports time per lookup across eight workers, not single-request latency.

`go test -race -count=1 ./core/workspace` passes on both main and the patch with the same added tests. The tests cover configuration edits and deletion, a nearer configuration, errors, oversized files, caller mutation, concurrent callers and warnings delivered to each caller.

To run the component benchmarks:

```sh
go test ./core/workspace -run '^$' -bench '^BenchmarkGitClientDeclarations$' -benchmem -benchtime=5000x -cpu=8
```

[Full-command measurements and methodology](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_CONFIG_DECLARATION_REUSE.md). [Current-main verification](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/assessment/config-declarations-oct19/README.md).
