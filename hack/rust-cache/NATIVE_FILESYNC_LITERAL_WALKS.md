Walking a single literal include directly improves complete Go collection listing from **55.81 to 52.03 seconds** in two balanced pairs. All commands succeed and preserve the expected rows. Median CLI CPU falls **39.50 to 26.81 CPU-seconds**, or 32%. Full-repository listing remains far too slow.

The [parent-walk diagnostic](NATIVE_FILESYNC_PARENT_WALKS.md) showed that filtered imports enumerate unrelated siblings at each ancestor. Parent synchronization repeats this preparation for every content snapshot. The native filesystem can inspect the ancestor chain directly, then walk the selected subtree, while retaining the ordinary include/exclude filter.

The standalone change is [c22eaa558](https://github.com/grouville/dagger/commit/c22eaa55863fb2ca22919119ff30e952f54f8076), based on current upstream `ff0b029a4`. It changes `internal/fsutil`, which the CLI actually uses for host imports. The filter receives the same ancestor records and subtree. Symlink, missing or unreadable ancestors fall back to the existing walk. Other filesystem implementations retain their walker. State is local to each call; there is no new lock, dependency, hash format or metadata-normalization change.

Both timing CLIs are built on `ff0b029a4`, retain the selected host glob pruning and artifact-output buffering, and report API version `v1.0.0-beta.15`. The Go module remains `7568cd0`. Engine binary `21b62c6cfe77dd2787c001097a0a28a003e65ec72496555ae70dcb060d2db111` runs throughout. Each command starts a fresh CLI and edits `dagql/types.go` on a warm engine. Telemetry and ordinary GC stay enabled. Profiling stays disabled. There is no restart, cache reset or forced GC.

| Pair | Order | Before | After | Rows |
| --- | --- | ---: | ---: | ---: |
| Initialization/correctness, excluded from medians | Before, after | 54.04 s | 51.87 s | 4,399 |
| Measured 1 | After, before | 54.66 s | 52.64 s | 4,398 |
| Measured 2 | Before, after | 56.96 s | 51.41 s | 4,398 |

The first pair adds a real test declaration in both arms. Measured pairs remove it, preserving every other row and its order. The two measured gains range from 2.02 to 5.55 seconds; the median gain is 3.79 seconds (6.8%). Engine CPU is 259.83 → 248.88 CPU-seconds and allocation is 36.89 → 36.23 GB in this cohort. The primary causal evidence is reduced host traversal and CLI CPU. Do not add this gain to earlier medians from other CLI builds or engine states.

Three alternating component pairs hold the selected three-level path constant and vary unrelated siblings:

| Siblings | Before | After | Allocated before → after |
| --- | ---: | ---: | ---: |
| 8 | 57.32 µs | 50.47 µs | 17.5 → 15.2 kB |
| 128 | 193.91 µs | 51.34 µs | 48.5 → 15.2 kB |
| 2,048 | 2.439 ms | 48.42 µs | 575.8 → 15.2 kB |

Each iteration verifies the same three emitted directory records. Cost becomes almost independent of sibling width. The large case improves about 50×; that is a component result, not a complete-command claim.

The full `internal/fsutil` and `engine/client` race suites pass. Added checks compare complete stats and order against the original walker, including hardlinks, symlink ancestors and targets, missing paths, Unicode, exclusions, mapping callbacks, early stops and cancellation. Linux checks verify xattrs and unreadable ancestors as an ordinary user; neither is skipped. The fast path explicitly checks cancellation before reporting completion. Existing Go collection, overlay, subdirectory-discovery and generation-glob checks pass.

A separate counter run completes successfully in 51.16 seconds with identical 4,398 rows. Native callbacks visit **237,287 entries**: **194,847 under parent-sync roots** and **42,440 under content roots**. The original diagnostic visits 5,581,952, including 5,351,714 under parent-sync roots. This is a 95.7% reduction in visited entries on this host. The counter is inside the native walker: an FS-interface wrapper would hide the optional method and accidentally disable the optimization. Its 6,320 native walk calls include short ancestor lookups and are not a count of RPCs.

The populated `/tmp` amplifies the observed cost, so the real-repository gain is specific to this development host. The controlled benchmark includes both narrow and wide cases. Counters observe entries before filtering, not transferred bytes or every filesystem syscall. Instrumented elapsed time is diagnostic, not another timing comparison.

[Prepared PR description](PR_FSUTIL_LITERAL_WALKS.md). [Source, checks, all component/full-command attempts and diagnostics](experiments/filesync-literal-walks/). No PR is open.
