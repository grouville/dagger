Go test collections search the whole Go module again while discovering each package's test names. With 16 packages and eight tests per package, the profile records 2,176 search-result item reads. Expanding more packages repeats work over every other package's tests.

Search each package's immutable test files instead. Keep the existing Rust-regex matcher and filename order, and use `Workspace.file` so workspaces assembled with `withDirectory` remain supported. The module-wide search used to discover package paths stays in place.

| Edited test command | Main | Branch | Allocated bytes, main → branch |
| --- | ---: | ---: | ---: |
| 16 packages, 128 tests | 4.52 s | 2.36 s | 3.50 → 1.19 GB |
| 64 packages, 512 tests | 55.11 s | 8.12 s | 40.92 → 4.47 GB |

Four balanced before/after pairs per size, with a fresh source edit and CLI process for every command. All eight pairs improve. The engine and compiler caches are warm; telemetry and ordinary garbage collection remain enabled, and profiling is off during timing. All observations, including the slower baseline runs, are retained. These measurements use the same diagnostic engine with existing scalar-array and collection-index improvements; only the Go module source changes between arms.

This does not batch package execution. At 64 packages, the module-wide test function takes 1.05 s and native Go takes 0.25 s. The remaining gap needs separate work.

The one-package, one-file control has the same 0.93 s median on both arms. Its median paired difference is a 29 ms slowdown, with only one of four pairs faster; it establishes no benefit for that small case. Allocations increase by about 6 MB. The large-case gains should not be presented as a general fixed-cost improvement.

A single package with 16 test files measures 1.30 → 1.38 s, with 2/4 faster pairs and an 85 ms median paired slowdown. It allocates 42 MB less and uses less engine CPU, but starts a search for each file. That is the explicit tradeoff for removing repeated module-wide result expansion. The branch adds no engine lock, cache format or dependency; both smaller controls remain part of the review.

The focused collection integration check passes on main and the branch, including test subsets, package isolation, failure reporting, nested modules, build constraints, stable ordering and workspaces assembled from directories. The added Unicode test and parameter names reject an earlier local-regex implementation and pass with the engine matcher used here. Formatting passes with the engine's Dang formatter.

Code: [grouville/go, perf/package-test-discovery](https://github.com/grouville/go/tree/perf/package-test-discovery), based on official Go module main `334136faaa`. [Raw measurements and validation](../experiments/rust-go-test-collections/) accompany the comparison. No upstream pull request is open.
