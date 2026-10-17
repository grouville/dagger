Host glob pruning improves complete Go collection listing from **58.10 to 53.76 seconds** in two balanced pairs. Both pairs return identical 4,398 rows and exit successfully. CLI CPU decreases **75.96 to 39.45 CPU-seconds**. The engine's CPU and allocation stay comparable; the remaining listing latency is unresolved.

`Workspace.glob("core/*_test.go")` reaches `engine/client.globHostPath` through the host filesync RPC. The existing shortcut handles literal patterns and a final `*` or `**`, but wildcard filenames still walk the whole checkout. Repeating those walks across packages wastes host CPU and filesystem work.

The selected change keeps walking from the workspace root and skips subtrees outside the literal directory prefix before the first pattern character. Keeping the original root preserves symlink handling and traversal order. Patterns without a fixed directory prefix and exclusion patterns retain their existing traversal. The implementation adds 13 lines and removes two; it introduces no dependency or shared state.

The full-command comparison uses identical CLIs built on `ff0b029a4d270a651b9a8c7286babc79089066e4`, with the previously selected artifact-output buffering in both. Both negotiate API version `v1.0.0-beta.15`. The Go module is `7568cd0e5309a716fc94f310a488978fd97ce0c3`; the same experimental engine binary, `21b62c6cfe77dd2787c001097a0a28a003e65ec72496555ae70dcb060d2db111`, runs throughout. These are not stock-engine measurements. Every command starts a fresh CLI and edits `dagql/types.go` on a warm engine. Telemetry and ordinary garbage collection stay enabled. No engine restart, cache reset, forced GC, CPU profiling or wcprof capture occurs during the paired timings.

| Pair | Order | Before | After |
| --- | --- | ---: | ---: |
| Initialization, retained separately | Before, after | 68.08 s | 50.93 s |
| Measured 1 | After, before | 58.12 s | 53.28 s |
| Measured 2 | Before, after | 58.07 s | 54.23 s |

The initialization pair is excluded from the medians. The selected change saves 4.34 seconds, or 7.5%, in this cohort. The first pair's larger gain is not the claimed result. Engine CPU is 247.59 → 249.04 CPU-seconds and allocation is 35.70 → 35.98 GB. These small differences do not establish an engine-side gain or regression. This result must not be added arithmetically to earlier gains measured with other CLI builds or engine states.

Three alternating component pairs use a 4,608-file fixture with a warm filesystem cache:

| Pattern | Before | After |
| --- | ---: | ---: |
| `module00/pkg00/*_test.go` | 8.33 ms | 0.085 ms |
| `module00/**/*.go` | 8.49 ms | 0.540 ms |
| `**/*.go`, full-tree control | 12.06 ms | 12.14 ms |

Scoped filename-glob allocation falls from 1.24 MB to 22.6 kB per call. The global control keeps its full traversal and shows no demonstrated improvement.

The full `engine/client` race suite passes on the standalone source. The new parity test compares exact results and order against an unpruned walk, including nested wildcard tails, character classes, escaped separators, Unicode, symlinks, missing prefixes and cancellation. Existing Go collection, subdirectory-discovery and generation-glob checks pass with a fresh fixture edit. Separate complete commands add and remove a real test declaration: 53.20 and 52.66 seconds, exactly 4,399 then 4,398 rows, preserving every other row and its order. No compilation or test workload starts during listing.

A second experiment also stops descending below simple filename globs. It passes the expanded parity tests and improves `*_test.go` on a 4,609-file fixture from 9.35 to 0.046 ms. Its separate full-command cohort takes 59.00 → 54.01 seconds, with successful, identical add/remove-test listings in both balanced pairs. This does not demonstrate an additional command-level benefit over prefix pruning alone. The extra syntax guards and traversal branch remain unselected; the standalone change keeps only the simpler prefix pruning. All attempts are retained.

The selected source is [standalone commit 2481e74b3](https://github.com/grouville/dagger/commit/2481e74b3e02d185d9ba566199e5f4dfdca28eca), based on `ff0b029a4`. The complete client race suite passes on that worktree without source overlays. The final test matrix adds parity cases for wildcard roots and escaped separators; implementation and measured benchmark source stay identical. No upstream PR is open.

A new diagnostic completes in 54.39 seconds with identical 4,398 rows, successful cleanup and 559,733 wcprof events, with no dropped events or open operations. Its main query spends 17.83 seconds discovering packages, approximately 16.8 seconds expanding their test collections, and approximately 9.45 seconds materializing collection metadata. Eight hundred `GoPackage.tests` invocations execute; the Go collection's 800 getters hit their cache. `dang.invoke` includes awaited API requests, so its duration must not be reported as interpreter CPU.

The CLI CPU capture samples 38.84 CPU-seconds. Filesync's sender walk accounts for 11.94 CPU-seconds, or 30.7%, in a stack distinct from the optimized host glob. wcprof records 1,213 executed `Host.directory` imports. The next filesystem investigation should count visits and inspect the actual filters for those imports before changing traversal or cache behavior. On the engine, sampled CPU still includes interpreter evaluation and allocation/GC; span export also remains significant. A separate natural GC takes 4.32 seconds, including 0.96 seconds of snapshot collection. No observed goroutine sample catches a blocking containerd root scan. These diagnostic observations do not establish another speedup.

[Prepared PR description](PR_CLIENT_HOST_GLOB_PREFIX.md). [Sources, complete attempts, correctness checks and profiles](experiments/host-glob-prefix/).

The follow-up [parent-directory walk counter](NATIVE_FILESYNC_PARENT_WALKS.md) completes successfully and attributes 95.9% of visited entries to parent-only preparation. No optimization is claimed from that diagnostic yet.
