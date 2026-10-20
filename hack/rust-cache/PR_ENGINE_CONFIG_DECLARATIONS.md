[Draft PR #14741](https://github.com/dagger/dagger/pull/14741)

Go test collection listing repeatedly parses `dagger.toml` to determine which Git clients a module may use. One full-repository profile showed 15,003 decodes of the same 1.6 kB file. This happens before the function-result cache lookup, because the declarations help determine its key.

Cache the parsed declarations by file contents. Every call still reads the file and finds the nearest configuration, so edits, deletion and changes to module scope take effect immediately. Each caller receives its own list and warnings.

On our development engine, holding the other performance changes constant and toggling only this cache improved the complete 4,398-row listing:

| Complete listing | Without this cache | With this cache |
| --- | ---: | ---: |
| Elapsed time | 45.51 s | 40.65 s |
| Engine CPU time | 218.89 CPU-s | 206.55 CPU-s |
| Bytes allocated by the engine | 35.06 GB | 32.75 GB |

Medians of four alternating pairs, faster in all four. Each starts a fresh CLI after a source edit and returns the correct ordered rows through successful cleanup. This is a warm engine, with telemetry enabled and normal garbage collection: about an 11% listing improvement in that setup.

**This stays draft: the full-listing gain on current main is not established.** New attempts with main, this LRU and a DagQL-cache alternative all reached 180 seconds without rows. They provide no completed-command comparison and do not show that the LRU beats DagQL end to end.

The existing LRU library retains at most 32 configurations. Files larger than 64 KiB are parsed without being retained. Concurrent callers share one decode outside the cache lock. The configuration helper needs no engine/session setup.

Component benchmarks against main `ce6dc9f9403b52067f5831149eab4871f857185d`, using the real Go configuration in four fresh-process pairs:

| Declaration lookup | Main | This change | Allocations per lookup |
| --- | ---: | ---: | ---: |
| Same contents | 324.93 µs | 3.99 µs | 2,818 → 3 |
| New contents every time | 335.41 µs | 351.06 µs | 2,823 → 2,826 |

New inputs cost about 4.7% more. Repeated-content lookups improve in all four pairs.

The workspace race suite passes on main and the patch. Tests cover edits, nearer configurations, errors, caller mutation, concurrent callers and warnings.

```sh
go test -race -count=1 ./core/workspace
go test ./core/workspace -run '^$' -bench '^BenchmarkGitClientDeclarations$' -benchmem -benchtime=5000x -cpu=8
```

[Full-listing measurements and profiles](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/config-content-declarations), [current-main component checks](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/assessment/config-declarations-oct19), [cache comparison and incomplete full-repository attempts](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/assessment/config-cache-full-listing-oct19).
