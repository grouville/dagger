# Batch Go package discovery

The final Go module revision improves complete listing after a test-file edit **17.35 → 15.92 seconds**, faster in all four balanced pairs. Ordinary-source edits improve **10.39 → 7.56 seconds**, faster in three of four pairs. All 40 commands across the initial and final cohorts return correct rows and exit successfully. Three seconds remains unachieved.

This change is in the Go module and its shared `gomod` library. Both arms use the same isolated engine binary, with getter content identity enabled in both. No engine source changes, new locks, external dependencies or cross-call caches are added.

The source is pushed to `grouville/go:experiment/batch-package-discovery`: `3525dec` introduces batching and `09518aac0858390722e71c82a719c2f6e131e611` confines the shared-index predicate to the new path. The branch builds on the preceding native test-snapshot prototype. No PR is opened; a standalone port and direct API adoption remain separate work.

## What changes

Discovery previously validated each module, then made further module calls to list its owned Go files. Resolving nested boundaries also called the library through SDK boundaries. With 80 modules, these repeated calls perform client, schema and configuration preparation before doing their small amount of work.

`Gomod.packageFacts` now returns validated module paths, prefixes, test selection and owned files in one module evaluation. It reads module boundaries once in the relevant scope and builds an immutable index with balanced merges. A caller inside an enclosing module still includes that module's sibling boundaries; a caller without an enclosing module does not scan unrelated workspace roots. Invalid `go.mod` files remain ownership boundaries even though they are excluded from the discovered modules.

The Go module constructs its owners from those facts and keeps package classification parallel through a local discovery object. The workspace mount is computed once. Existing public module discovery and ownership methods retain their behavior; the global-index rule applies only to the batch path. Roots and files are read afresh for each invocation.

Index construction costs O(B log B) for B boundaries; ownership checks follow a file's path ancestors. Existing sorting costs remain. Per-test collection keys, subsets, selection and execution keep their existing paths. This is ordinary Dagger module composition with fewer calls.

## Final complete-command results

Command: `dagger check --module go --check test --list --all`, on real dagger/dagger source at `ff0b029a4d270a651b9a8c7286babc79089066e4`.

| Workload | Before | Final batch revision | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 17.35 s | **15.92 s** | 4 / 4 |
| Ordinary-source edit | 10.39 s | **7.56 s** | 3 / 4 |

For test-file edits, median engine CPU is **95.98 → 91.94 CPU-seconds** and cumulative allocation **18.68 → 17.39 GB**. CPU improves in two pairs; allocation improves in every pair. The median paired latency saving is **1.38 seconds**.

For ordinary-source edits, median CPU is **43.80 → 35.41 CPU-seconds** and allocation **7.91 → 6.33 GB**. CPU and allocation improve in three pairs. The median paired latency saving is **2.26 seconds**. The first candidate, which removes the initialization test, takes **14.98 seconds** against the control's 11.66 seconds; it is retained. Subsequent candidates take 7.36, 7.52 and 7.60 seconds.

Every arm starts a fresh CLI on a warm engine and edits an ordinary Go source file. The test-edit cohort also changes a real test file on every invocation. Each cohort has an initialization pair adding a real test and returning 4,399 rows; all measured commands remove it and return identical ordered 4,398 rows and full row text. Initializations are excluded from medians. Full exit, session cleanup and final log flush are included. Telemetry and normal GC remain enabled; timing runs have no profiler or concurrent tests/builds. All sources, config and experiment flags are restored.

Final test-edit host CPU pressure peaks at 16.4%, I/O below 0.19% and memory pressure is negligible. For ordinary-source edits, CPU pressure peaks at 26.1%, I/O below 0.13% and memory pressure is negligible. These conditions and every sample are archived.

The initial revision's separate cohorts measured **17.61 → 15.16 seconds** for test-file edits and **9.75 → 7.62 seconds** for ordinary-source edits. Their raw attempts are retained. The final figures above supersede those results; gains must not be added to each other or to preceding experiments.

## Correctness and scope

Seven focused checks pass on the final source: Go discovery, package-layout rebinding, test collections, and library package facts, owned files, discovery and lookup. Execution checks inspect generated binaries. The added library check compares the new API with existing discovery and ownership results on the host fixtures and native workspaces. It also asserts expected results independently for invalid and empty modules, modules containing only ignored or nested code, sibling names such as `a` and `a-b`, Unicode byte order, overlays and changed cwd, including no enclosing module.

An adversarial review found that a global index contains a module itself and its ancestors, while the existing helper accepts a descendant index. The second commit applies the extra filtering only to the batch path, preserving the existing public helper's predicate. Final timings and all seven checks run after this refinement.

No broad engine race run is repeated for this module-only change. The previous engine's focused race validation remains inherited; the full remaining Go-module suite is not rerun. These are limits on adoption evidence, not a claim of complete compatibility across every tool and SDK.

## Profiles and next bottleneck

Lossless before/after captures show **964 → 804 Dang evaluations** and **3,803 → 2,293 nested SDK requests**. The 80 `workspaceRootPath` and 80 `ownFiles` evaluations disappear from collection discovery, replaced by one `packageFacts` evaluation. Both captures preserve **799 test-discovery hits and one execution**. All 800 package getters still execute.

The final revision is captured again with wcprof and CPU profiling: **259,962 events**, no drops or open operations, the same 804 evaluations and 2,293 SDK requests, correct rows and successful exit. This diagnostic takes 18.17 seconds; it is not another latency comparison. Root discovery occupies about 7.36 seconds in its 17.70-second main query; getter work follows. Earlier unprofiled-mode captures have different durations.

The CPU recording covers 20.11 seconds, including the end of the command and subsequent activity, and contains 102.48 CPU-seconds across cores. It identifies **8.91 CPU-seconds in `context.(*valueCtx).Value`**, mainly reached through Dang's `GetEvalContext` (6.44 seconds), `forcingInChain` (1.16 seconds) and `withForceChain` (0.91 seconds). The first five-second window also shows substantial lookup cost, so it is not confined to shutdown. GC is another major sampled cost. CPU durations overlap through their call stacks and are not wall-time savings.

The compiled code confirms that evaluation and force-chain state are added with separate `context.WithValue` wrappers, and every `EvalNode` retrieves evaluation state through the context. The next algorithmic experiment is bounded lookup of these private interpreter values while preserving raw values, source error context, cancellation, deadlines and initializer-cycle detection. Prove it with focused tests and a depth benchmark, then measure the complete command. This introduces no language API or cache-key shortcut. The earlier native-sort and known-ID experiments should not be reselected without new evidence.

## Reproduction

[Evidence archive](experiments/batch-package-discovery/) includes the exact initial and final sources, patches, all 40 timing commands, checks, restoration and pressure data, three lossless wcprof captures and CPU profiles. The engine and CLI are unchanged from [collection getter content identity](NATIVE_COLLECTION_GETTER_CONTENT.md): engine `bcb54624de35daa61dbf801a9bfd303ea986c838d95932374f808c49caa131a7`, CLI `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`.

The diagnostic engine remains `dagger-collection-content-oct18`, with its own volume, runner port 16277 and debug port 16105. Getter identity, known-input IDs and profiling are restored to disabled. The original engine binary and retained cache volume are neither replaced nor reset.

[Prepared review description](PR_GO_BATCH_PACKAGE_DISCOVERY.md) states the measured benefit and the standalone-port requirement. No PR is opened.
