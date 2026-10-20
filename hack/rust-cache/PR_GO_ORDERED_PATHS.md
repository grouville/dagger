While profiling Go test collection listing on `dagger/dagger`, I found that ordering the owned-file list was doing millions of unnecessary comparisons. Even when the next path was already in order, the helper walked the earlier paths again to find where to insert it.

Check the last path first. If the new path belongs after it, append it; otherwise use the existing insertion code. The three private sorting helpers keep the same byte ordering and duplicates.

The complete file-discovery command on the real Dagger repository returns the same 2,511 paths:

Install this repository's `gomod` module in a Dagger checkout, then run `dagger api call gomod at --path=. own-files --glob='*.go'`.

| `gomod at --path=. own-files --glob=*.go` | Main | This change |
| --- | ---: | ---: |
| Elapsed time | 19.76 s | 3.15 s |
| Engine CPU time | 49.27 CPU-s | 6.54 CPU-s |
| Bytes allocated by the engine | 19.72 GB | 2.13 GB |

Four alternating measured pairs, faster in all four. Both versions use the same module path, engine and CLI. Every command starts a fresh CLI after a source edit, validates all filenames and their order, and completes cleanup. The engine and filesystem are warm; telemetry and normal garbage collection remain enabled. Separate wcprof captures confirm that both versions execute `ownFiles` and `Workspace.glob`.

These numbers measure owned-file discovery, which is part of preparing the Go test collection. **They are not a full test-listing result.** The comparison uses Go main `8a1d6ad09c909a541e7e5fa319bddb5dba83d20b` and an otherwise unchanged Dagger engine/CLI from main `23b004afe665eb4cc8a44767ba532fcb5cda2020`.

The cost is one extra check per item when the paths are out of order. A component comparison of the actual helpers in the stock interpreter shows the trade-off:

| 512 strings | Main | This change |
| --- | ---: | ---: |
| Ascending | 674.49 ms | 6.54 ms |
| Reverse order | 10.62 ms | 14.63 ms |
| Shuffled | 341.75 ms | 352.97 ms |

The original insertion fallback remains quadratic, and appending still copies lists. This targets the mostly ordered paths returned by file discovery, rather than providing a general-purpose faster sort.

The added public check covers empty, singleton and ordered file lists, including Unicode and `a.go` versus `a/b.go`. It passes on main and the patch. The existing test-collection integration check also passes on both, including nested modules, stable names and actual selected test execution. Dang formatting passes.

```sh
dagger check --module gomod-checks --check file-order-check
dagger check --module go-dev --check tests-collection-check
```

[Raw command results, component controls, source identities and wcprof checks](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/assessment/go-ordered-paths-oct20).
