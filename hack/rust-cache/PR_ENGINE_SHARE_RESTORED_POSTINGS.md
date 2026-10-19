# perf(dagql): share result lists when restoring the cache

While investigating slow Go test collection listing on dagger/dagger, I found that the engine was doing unnecessary work when restoring its cache and deleting old results.

The cache can find the same saved results through several different keys. When the engine restores the cache, it copies the list of results for every key. With 1,000 keys pointing to the same 1,000 results, that means storing a million entries instead of one shared list.

This PR shares that list between the keys. It also tracks which lists contain each result, so deleting a result updates each shared list once instead of repeating the work for every key.

Sharing must preserve what each key can find. In particular, adding a new result to one key must not make it available through the other keys. Those later additions stay separate; only the original list is shared.

The cost is extra tracking for cleanup. This should help most when many keys share a large list, as we saw during the Go listing investigation. It may be less efficient when each list contains only one result; that case still needs measuring. All access uses the existing cache lock.

### Results

Comparing main `80699ac67a` with only this change applied:

| Operation | Main | This PR | Memory allocated, before → after |
| --- | ---: | ---: | ---: |
| Restore 129 results | 7.31 ms | 4.66 ms | 2.41 → 1.58 MB |
| Restore 2,049 results | 713.15 ms | 49.53 ms | 227.81 → 25.91 MB |
| Delete 2,049 results | 844.75 ms | 12.75 ms | 3.95 → 3.95 MB |
| Delete 8,192 results | 31.43 s | 45.59 ms | 16.01 → 16.01 MB |

Medians from four pairs of runs, alternating which version runs first. This change was faster in every pair. The filesystem cache was warm; setup and cache closing are excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

These measure cache restoration and cleanup. The effect on the complete Go test listing command has not yet been measured for this change alone.

### Reproducing

The regression tests check that sharing preserves which results each key can find, including after additions and deletions:

```sh
go test -race -count=1 ./dagql
```

To run the restoration and cleanup benchmarks added by this PR:

```sh
GOMAXPROCS=8 go test ./dagql -run '^$' -bench 'Benchmark(CacheImportWideOutputClass|MetadataPruneRestoredWideOutput)/(64|1024|4096)$' -benchmem -benchtime=1x
```

[Raw measurements and instructions for running the same benchmarks against main](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/restored-index).
