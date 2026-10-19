# perf(dagql): share result lists when restoring the cache

While investigating slow Go test collection listing on dagger/dagger, I found that the engine was doing unnecessary work when restoring its cache and deleting old results.

The cache can find the same saved results through several different keys. When the engine restores the cache, it copies the list of results for every key. With 1,000 keys pointing to the same 1,000 results, that means storing a million entries instead of one shared list.

This PR shares that list between the keys. It also tracks which lists contain each result, so deleting a result updates each shared list once instead of repeating the work for every key.

Sharing must preserve what each key can find. In particular, adding a new result to one key must not make it available through the other keys. Those later additions stay separate; only the original list is shared.

The cost is extra tracking for cleanup. With 2,048 separate one-result lists, restoring the cache is about 2% slower; adding 2,048 fresh results is about 3% slower. The benefit therefore depends on how much the keys share. All access uses the existing cache lock.

### Results

Each row compares the same cache contents on main `80699ac67a` and with only this change applied. The rows use different cache layouts:

| Cache contents and operation | Main | This PR | Memory allocated, before → after |
| --- | ---: | ---: | ---: |
| Restore two large shared lists, 2,049 results total | 713.15 ms | 49.53 ms | 227.81 → 25.91 MB |
| Remove 8,192 results from large shared lists | 31.43 s | 45.59 ms | 16.01 → 16.01 MB |
| Restore 2,048 separate lists, one result each | 39.75 ms | 40.53 ms | 23.69 → 23.75 MB |
| Add 2,048 fresh results | 38.57 ms | 39.81 ms | 15.38 → 15.31 MB |

The first two rows benefit from sharing: many keys point to the same large lists. The third row has little to share, so the extra cleanup tracking makes restoration about 2% slower. Fresh insertion is about 3% slower in the fourth row.

The shared-list cases use four alternating pairs, one operation per sample. The cost controls use six alternating pairs, one second per case. All shared-list pairs improved; the separate-list and fresh-result controls were slower in five of six and four of six pairs respectively. Restoration uses a warm filesystem cache; setup and closing are excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`. All raw observations are retained.

These are cache-operation timings. The effect on the complete Go test listing command has not yet been measured for this change alone.

### Reproducing

The regression tests check that sharing preserves which results each key can find, including after additions and deletions:

```sh
go test -race -count=1 ./dagql
```

To run the restoration, cleanup and cost-control benchmarks added by this PR:

```sh
GOMAXPROCS=8 go test ./dagql -run '^$' -bench 'Benchmark(CacheImportWideOutputClass|MetadataPruneRestoredWideOutput)/(64|1024|4096)$' -benchmem -benchtime=1x
GOMAXPROCS=8 go test ./dagql -run '^$' -bench '^BenchmarkResultList(SingletonImport|FreshInsert)$' -benchmem -benchtime=1s
```

[Raw measurements and instructions for comparing against main](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/restored-index).
