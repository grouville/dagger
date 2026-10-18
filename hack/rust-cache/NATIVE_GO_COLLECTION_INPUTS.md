# Live inputs and repeated collection execution

A diagnostic with frozen real test names improves **11.92 → 1.07 seconds median** when its child collections stop accepting an unused live `Workspace`. All four measured pairs improve, with identical ordered 4,398 rows and successful cleanup. Lossless wcprof confirms **800 child executions become 800 cache hits**. This is a structural control, not a real Go-module optimization. The last selected real-module comparison remains **25.45 → 19.21 seconds**.

## The one-line control

The existing diagnostic fixture exposes the same 800 package keys and 4,398 frozen names through ordinary nested collections. It cannot execute checks and does not discover current source. Both variants retain the root `packages(ws: Workspace!)` method. The only source difference is its child declaration:

```dang
# Before: the body reads only its stored path and frozen names.
tests(ws: Workspace!): GoTests! { ... }

# Control: identical body and collection path.
tests: GoTests! { ... }
```

The input is genuinely unused in this fixture. Removing a live input from the real module, whose body reads it, would change behavior. The fixture's names are unsuitable for a production module.

Both arms use the same engine, CLI, retained volume and source checkout, with typed artifact metadata and generic immutable-data projection enabled. Every command starts a fresh CLI and edits a Go source comment. Telemetry, ordinary GC, cleanup and a final log flush stay included. Profiling is off during timing. There is no reset, forced collection, budget change or deferred cleanup.

| Measured pair | Live child input | Unused input removed |
| --- | ---: | ---: |
| 1, candidate first | 9.54 s | 1.070 s |
| 2, control first | 11.99 s | 1.070 s |
| 3, candidate first | 11.84 s | 1.069 s |
| 4, control first | 14.60 s | 1.371 s |
| Median | **11.92 s** | **1.070 s** |

All ten commands succeed, including an excluded initialization pair of **13.60 → 5.54 seconds**. These initialization costs are retained; the 1.07-second result describes a warm engine with populated child results. All commands return the same full ordered rows. The fresh source edits do not alter the frozen fixture's names, so this is not evidence of fresh real-source discovery or edited-build performance.

Median engine CPU falls **32.58 → 1.99 CPU-seconds**, and cumulative allocation **4.68 GB → 458 MB**. Both improve in every measured pair. Host CPU pressure reaches 18.9%; I/O pressure stays below 0.08%. All observations, including maintenance overlap and the slower last candidate, remain included. These results must not be added to or subtracted from earlier cohorts.

## Verify what disappeared

Separate diagnostic captures return correct rows with no dropped events or unfinished operations:

| Operation | Live child input | Unused input removed |
| --- | ---: | ---: |
| `GoPackage.tests` executions | 800 | 0 |
| `GoPackage.tests` cache hits | 0 | 800 |
| Dang function evaluations, including root | 801 | 1 |
| Nested SDK requests | 0 | 0 |
| Wcprof events | 116,155 | 62,507 |

The captures complete in 12.50 and 1.07 seconds respectively. They are not additional benchmark samples. The control demonstrates the cost of executing hundreds of child methods even when they perform no SDK requests. Existing result reuse can list this collection quickly. It does not prove that removing queries, schema cloning or a lock alone would yield this gain on the real repository.

## Reject the owner-index detour

A separate real-module experiment builds an owner map using balanced merges and looks up a package's directory prefixes. It preserves the `go.mod` layout guard and legacy fallback. Four focused checks pass, including retained-package rebinding and a new execution case with root, nested and similarly named sibling modules. An initial constructor exposing a map is rejected by the SDK; the corrected version keeps the map private and preserves constructor arguments.

Complete real listing regresses **17.61 → 19.05 seconds median**, faster in only one of four alternating pairs. All ten commands return correct rows and exit successfully. CPU medians increase **91.94 → 93.91 CPU-seconds**, and allocation **16.84 → 17.16 GB**. The last pair is especially slow, **20.53 → 31.42 seconds**, and remains included. The candidate is unselected; no PR description is prepared for it.

The existing profile already records all 800 `GoPackages.get` calls as cache hits in the edited-source case. The linear ownership scan executes when a getter needs evaluation, so it was a poor target for this warm workload. The index also stores additional state. No complete-command gain is established, and the 21 prepared additional checks were not run after rejection. Sources, the new regression, four passing checks, the initial SDK error and every measurement are retained.

## Refine the allocation diagnosis

Focused analysis of the latest real-module CPU capture attributes about **1.64 CPU-seconds** to schema forks and **4.21 CPU-seconds** to interface reconciliation, out of **92.68 sampled CPU-seconds**. These cumulative stacks overlap. They can amplify admission contention, but do not by themselves explain the desired order-of-magnitude improvement. Previous schema-reuse counterexamples still apply; no rejected variant is re-enabled.

A subsequent real listing with allocation profiling and lossless wcprof completes in 20.89 seconds with correct rows. Memstats records **17.93 GB allocated** and two natural GCs. The 25-second delta allocation profile contains only **5.08 GB** of sampled allocation. Go's memory profile can lag by up to two GC cycles, so its sample percentages must not be presented as shares of the complete command. No GC is forced to fill the profile.

Within that sample, callback evaluation and scope construction are prominent. The sample attributes about 2.37 GB cumulatively beneath `callFunc`, including overlapping `reduce`, `filter` and `map` paths; those values must not be added. It attributes about 173 MB beneath interface reconciliation. These are allocation clues, not evidence that every callback or ownership scan executes on each edited listing. The cache-hit check above invalidates the ownership hypothesis.

## Direction for the real module

The useful next prototype is discovery that produces immutable data for child collections. Read current source at the discovery boundary, retain native Directory/File snapshots and parsed test metadata, then let ordinary Dagger result caching reuse unchanged children. The current real module still performs 800 `GoPackage.tests` evaluations and 4,845 nested SDK requests; neither is needed to emit cached names in the control.

A real implementation must observe new and removed tests, preserve file order, Unicode, workspace overlays and nested-module ownership, and retain execution against an explicitly supplied workspace. The current `GoPackage.tests(ws)` API permits retained packages to rebind to an edited layout; its live input cannot simply be dropped. An experiment may compare another data flow, but its API and compatibility tradeoffs need to remain explicit. First measure fresh real-source edits through the complete command before adopting it.

The engine and CLI are unchanged (`1a514c53` and `97f7d82d`), source remains `ff0b029a`, and the selected module baseline is `0b487434`. Temporary controls and configuration are restored. No engine restart, native Rust cache change or PR occurs. [Evidence](experiments/collection-live-inputs/) includes both completed comparisons, exact sources, setup failure, CPU and allocation attribution, lossless captures and restoration state.
