# perf(dagql): skip disk-usage bookkeeping for values with no disk data

While profiling Go test collection listing on dagger/dagger, I found that preparing cache cleanup did substantial work for values that have no disk data, such as numbers, strings and collection metadata. It created a measurement record and took a temporary reference for each one.

Skip that bookkeeping when a value has no disk-usage provider, no snapshot links and no previous measurements to clear. Before using the measurements, cleanup still checks whether the value changed: a number replaced by a value with disk data must be measured before pruning proceeds.

This adds a check per value. The saving depends on how many values have no disk data; a cache made entirely of disk-usage providers still takes the normal measurement path.

### Results

Comparing main `80699ac67a` with only this change:

| Operation | Main | This PR | Memory allocated, before → after |
| --- | ---: | ---: | ---: |
| Prepare disk cleanup, 200,000 scalar results | 998.88 ms | 459.68 ms | 158.94 → 91.12 MB |
| Sample 128 disk-usage providers, control | 138.60 µs | 141.54 µs | 87.63 → 87.63 kB |
| Sample 2,048 disk-usage providers, control | 3.11 ms | 3.05 ms | 1.52 → 1.52 MB |

Medians from four alternating pairs. Cleanup preparation improved in every pair. Provider-only timings were mixed at 128 results and faster in three of four pairs at 2,048, with unchanged allocation counts. The large fixture uses one operation per sample; controls run for 300 ms. Setup is excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

These are cache-operation measurements. The complete Go listing gain has not yet been measured for this change alone.

### Reproducing

The regression tests check both changes of state: a value gaining a disk-usage provider must be measured, and a value losing one must have its old size cleared:

```sh
go test -race -count=1 ./dagql
```

To run the cleanup benchmark:

```sh
GOMAXPROCS=8 go test ./dagql -run '^$' -bench '^BenchmarkCachePruneSnapshot/disk/200000$' -benchmem -benchtime=1x
```

[Raw measurements and instructions for reproducing both the benefit and provider controls](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/usage-sampling).
