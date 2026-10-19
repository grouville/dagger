# perf(fsutil): avoid listing unrelated directories for a single include

Closed pending evidence that the real-workload saving on current main justifies the added filesystem traversal logic. [Assessment](https://github.com/dagger/dagger/pull/14733#issuecomment-6275861689).

While investigating slow Go test collection listing on dagger/dagger, I found repeated host imports that selected a single path but still listed unrelated directories on the way to it. Importing `a/b/selected`, for example, first lists the root's other entries, even though none can be included.

For a single include with no wildcards, let the native filesystem visit the path's ancestors directly, then walk the selected subtree. The existing filter still receives the ancestors and selected entries in order.

This adds checks that each ancestor is accessible before taking the shortcut. If an ancestor is a symlink, missing or unreadable, use the original walk. Wildcard includes also keep the original walk.

### Results

Comparing main `80699ac67a` with only this change. The fixture imports `a/b/selected` and varies the number of unrelated directories at the root:

| Fixture | Main | This PR | Memory allocated, before → after |
| --- | ---: | ---: | ---: |
| 8 unrelated root directories | 59.17 µs | 51.27 µs | 17.53 → 15.17 kB |
| 128 unrelated root directories | 199.46 µs | 51.90 µs | 48.46 → 15.17 kB |
| 2,048 unrelated root directories | 2.51 ms | 49.87 µs | 575.80 → 15.17 kB |
| Wildcard include, 128 root directories | 1.19 ms | 1.08 ms | 78.85 → 78.83 kB |

Medians from four alternating pairs. All literal cases improved in every pair. The wildcard control was faster in three of four pairs with unchanged allocation counts; it still takes the original walk. Literal samples run for 100 ms, the control for 300 ms, with a warm filesystem cache. Fixture creation is excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

The extra ancestor checks matter most when there are few unrelated entries to skip; the eight-directory case includes that cost. These measure the filesystem walk, not the complete listing command.

### Reproducing

The tests compare paths, ordering and metadata against the original walk, including symlinks, missing paths, permissions, exclusions and callback errors:

```sh
go test -race -count=1 ./internal/fsutil ./engine/client
```

To run the literal-path benchmarks:

```sh
GOMAXPROCS=8 go test ./internal/fsutil -run '^$' -bench '^BenchmarkFilterFSLiteralInclude$' -benchmem -benchtime=100ms
```

[Raw measurements and instructions for reproducing the literal and wildcard cases](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/literal-import).
