The smaller sampler improves complete Go test collection listing **49.10 → 45.40 seconds median**, faster in all four measured pairs. Every command returns the expected rows and exits successfully. Real-cache preparation improves **5.12 → 3.22 seconds**, with the same results and measured usage and about 566 MB less allocation. The production patch passes the full DagQL race suite. Earlier versions regress on provider-heavy graphs and must not be proposed as-is. No PR is open.

One aligned five-second CPU window contains 5.64 sampled CPU-seconds, with 4.97 under `Cache.Prune`. A goroutine snapshot shows disk-prune snapshot construction holding the cache graph lock. Concurrent publication calls wait up to 2.95 seconds and finish together. The earlier snapshot-maintenance timer omits this preceding preparation. These observations come from the running engine's actual cache path. Logging contention appears elsewhere; telemetry remains enabled.

The candidate omits usage inputs and temporary ownership for values that cannot contribute disk usage and have no old measurements to clear. Previously sampled providers use the original validation path. Finalization scans current results again: an omitted value that becomes a provider still prevents physical reclaim until sampled. Unmaterialized snapshot links and old measurements remain included. Consumers treat absent and empty identity lists identically. Cache keys, persisted data and eviction policy retain their existing paths.

Against upstream `ff0b029a4d270a651b9a8c7286babc79089066e4`, the diff is 19 added and two removed implementation lines, plus two correctness checks. The full production DagQL race suite passes in 65.401 seconds of test execution. Both diagnostic paths pass focused usage/prune race checks. The comparison switches and routes are outside the proposed patch.

Three alternating pairs use fresh processes and normally published results, `GOMAXPROCS=8`, one benchmark iteration and fixture construction outside the timer. Every observation preserves 200,000 rows. The provider fixture shares one identity and checks a total of 64 bytes, deliberately exercising a case with little work to omit.

| Median per full disk snapshot | Upstream | Smaller candidate |
| --- | ---: | ---: |
| Metadata-only time | 589.98 ms | 334.68 ms |
| Metadata-only allocated bytes | 158,934,504 | 91,121,368 |
| Metadata-only allocations | 1,602,878 | 1,200,280 |
| Provider-only time | 840.05 ms | 732.88 ms |
| Provider-only allocated bytes | 296,351,856 | 296,351,856 |
| Provider-only allocations | 2,002,912 | 2,002,912 |

Both cases improve in all three pairs. The complete-command comparison below measures the user-facing result separately. The diagnostic engine restarts gracefully on its existing volume, with strict first-call Rust-cache reuse checked before and after restart. No cache reset or forced GC is used.

The sampler-only diagnostic engine is `1f6f09ef9164a5487676baedfdf285444517bbd61ed11a6941db38dd2162b2a6`, using production commit `9123b2e76bc59146de9e3f4c2505efb6f9f7d648`. Its graceful restart preserves the existing volume. All six Rust histories retain their expected 130/130, 1,026/1,026 and 6/6 action hits before restart and on their first calls afterward.

A separate non-evicting comparison prepares the full disk-prune state on the retained cache, serialized with ordinary GC. One initialization pair is excluded; four pairs alternate order. Every pair covers 854,567 rows and 6,017,660,136 measured bytes. Median preparation is **5.124 → 3.220 seconds**, faster in all four pairs. Median allocated bytes fall **1,060,766,208 → 494,879,852**, and allocations **11,216,845.5 → 7,792,172**. The legacy lazy-map option is off in both arms. No eviction, cache reset, source edit or forced GC occurs in this component comparison.

The full command is `dagger check --module go --check test --list --all` on source `ff0b029a` with the selected Go module `7568cd0` and CLI `e7ba08d`. Each invocation starts a fresh CLI and edits a used source file on the same warm engine. One excluded initialization pair adds a real test; measured pairs remove it. Normal telemetry and GC remain enabled, with no profiling. Prepared-schema reuse is off, and the policy-preflight experiment is absent; declaration reuse and linear restored-posting removal are common.

| Pair | Original sampler | Smaller sampler |
| --- | ---: | ---: |
| Initialization, excluded; 4,399 rows | 68.25 s | 55.99 s |
| 1, candidate first | 49.10 s | 45.56 s |
| 2, control first | 49.09 s | 45.33 s |
| 3, candidate first | 48.45 s | 43.25 s |
| 4, control first | 49.43 s | 45.47 s |
| Measured median | **49.10 s** | **45.40 s** |

All ten commands are correct and exit 0. Every measured command lists the same 4,398 ordered rows. The candidate is faster in all four pairs, with **3.86 seconds median paired saving**. Median engine CPU is 242.32 → 232.31 seconds and allocation 37.18 → 36.41 GB. Ordinary GC overlaps differ, so these are observations for this retained engine and cannot be added to savings from earlier cohorts. Listing is still far from the target. A separate wcprof, CPU and allocation capture follows the cohort; its profiled duration is not a benchmark observation.

The initial implementation, `0ac9ad557f292615446046395197cf36f12f4196`, checks each row before validating its existing sample. Its metadata benchmark improves 521 → 312 ms. Real-cache preparation improves 5.55 → 3.20 seconds over four pairs, preserving 854,531 results and 6,017,660,136 measured bytes. A separate full Go listing cohort takes 58.05 → 54.18 seconds median, faster in three of four pairs, with all ten commands correct and successful. Ordinary GC overlaps differ, so individual savings cannot be attributed wholly to the patch. These numbers belong to that initial implementation.

The provider check then exposes a regression, 663 → 826 ms with unchanged allocations. A second version combines classification, revision checks and capture in one payload read, but still regresses 729 → 848 ms over three pairs. Both versions are rejected. The smaller candidate restores the original sampled-provider validation path and classifies only new or changed inputs.

A separate policy-preflight experiment avoids building a graph snapshot when measured usage already meets the policy. Its no-target fixture improves 472 → 133 ms, but that shortcut never fires in the real full-command cohort. It remains separate from this proposal. The initial engine contains both experiments; the new comparison engine contains only the sampler change. A duplicate helper prevents the first generated comparison overlay from building; correcting that overlay lets both diagnostic race checks and the engine build pass. The production patch passes independently.

The post-cohort strict checks, with the candidate enabled, preserve all six native Rust histories again. The diagnostic sampler is restored off afterward. The full wcprof/CPU/allocation capture returns the correct 4,398 rows and exits 0, recording 569,840 events with none dropped or open. Its 50.62-second profiled duration is outside the timing cohort. The CLI CPU capture uses the existing `CPUPROFILE` option, which also records its runtime trace; engine allocation snapshots use no forced GC.

The sampled allocation difference totals about 34 GB. `dang.NewType` accounts for 2.24 GB of flat allocation. Cumulative sampled stacks beneath original span export and log conversion account for 2.81 GB and 1.54 GB respectively, including protobuf JSON work. The critical path still attributes 33.29 seconds of its 48.44-second root to Dang API requests. These spans encompass engine work and waiting; they do not establish that transport itself consumes that time. Cumulative allocation and CPU frames overlap.

The simple [lazy type-map constructor](NATIVE_DANG_TYPE_MAPS_CONFIRMATION.md) already has a flat full-listing comparison, so its visible allocation is not a reason to repeat that unchanged variant. A different source-confirmed target is `BoundBuiltinMethod.Call`, which constructs a temporary type and object solely to carry its receiver into the callback. Removing those allocations requires preserving callback scope, defaults and custom behavior; it has no measured speedup yet. The existing direct stored-span forwarding prototype also remains unselected. The new profile gives targets to measure without dropping telemetry records or introducing an unrelated global cache.

The [review description](PR_ENGINE_SKIP_EMPTY_USAGE_SAMPLING.md) includes the final implementation and complete-command comparison. [Source and evidence](experiments/cache-usage-provider-rows/) retain every attempt, source variant, profile, build command, mode, ordered output and cache-reuse check. The refined commit is pushed to the [fork branch](https://github.com/grouville/dagger/tree/perf/skip-empty-usage-sampling); no PR is open.
