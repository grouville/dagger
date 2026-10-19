# Three-second Go collection listing

The goal is complete listing on real dagger/dagger after an edit, with a fresh CLI, current-source rows, normal telemetry and successful session cleanup. The implementation must also support selection and real test execution through the Go and Rust modules, with native Rust compilation-cache reuse. A faster list is partial evidence until that workflow remains correct.

## Preserve the full workflow

| Stage | Required behavior |
| --- | --- |
| Source and module discovery | Read current files and configuration; honor overlays, nested module boundaries, ownership and exclusions. |
| Collection getters | Keep per-key cache lookup and execute the authored getter on a miss. Each invocation owns its current client, arguments, receiver state, initialization, failures, cancellation and resources. |
| Test discovery | Use native immutable source snapshots. Refresh changed test names while reusing unchanged package discovery. |
| Selection and execution | Run the selected tests through the public module APIs. Preserve expected failures and exclude invalid neighboring packages when unselected. |
| Compiler cache | Preserve native Rust artifact and incremental snapshots, including edits and restoration of earlier source versions. Measure edited builds separately from already compiled test execution. |
| Command completion | Include telemetry, output, final flushing and session cleanup in complete-command timings. |

Preparation can be shared when its identity and lifetime are proven independent of an invocation. Compiled declarations and their retained schema are examples with existing source/schema keys and initialization guards. Grouping getter setup remains an experiment: sharing a live client or changing which initializers execute requires its own correctness proof. An explicit stored-data collection has valid uses, but does not establish a general replacement for function getters.

## Current measured state

The latest interpreter candidate reuses the empty synthetic caller for concrete Dang callbacks while retaining fresh invocation scopes. Complete test-edited listing improves **10.01 → 9.53 seconds median**, ordinary-source listing **6.75 → 6.13 seconds**, faster in all eight balanced pairs. It removes roughly 1.1 GB of allocation. Test-edited profiles retain all 800 getters and 799 unchanged test-discovery hits; source-only profiles retain three evaluations and 572 SDK requests with all getters/discoveries hitting. The standalone patch passes the full race suite on pristine interpreter source, and development interpreter/SDK race suites plus 37 Go/Rust pipeline cases also pass. An unsafe unconditional-sharing variant fails the custom-callable regression. The diagnostic flag is restored. [Patch, review description, evidence and limits](NATIVE_DANG_CALLBACK_CALLER.md).

The preceding module candidate retains indexed ownership facts and shared tool settings instead of all full module owners. Complete test-edited listing improves **11.47 → 9.56 seconds median**, ordinary-source listing **6.54 → 6.21 seconds**, faster in all eight balanced pairs. All 800 getters execute, with 799 unchanged test-discovery hits. Getter receiver data falls **81.4 → 52.1 MB** and converted lists **392,000 → 6,400**. Nine checks pass, including real test, binary and generate execution with custom settings; a settings-loss negative control fails as expected. All 24 timing commands return correct rows and exit successfully. The candidate and its regressions are pushed to the Go fork; no PR is opened. [Implementation, evidence and limits](NATIVE_GO_INDEXED_OWNER_FACTS.md).

The preceding getter-preserving candidate reuses schema metadata already retained with eligible compiled module declarations. Complete test-edited listing improves **11.92 → 10.86 seconds median**, faster in all four pairs. Ordinary-source listing is flat at **6.43 → 6.45 seconds**. Both versions execute all 800 getters and retain 799 unchanged test-discovery hits; schema opens fall **804 → 2**. Six Go checks, eighteen actual module-source edit probes and 28 Rust/native-cache cases pass with their expected outcomes. The flag is restored to disabled. This remains a development-stack candidate dependent on the declaration-reuse prototype. [Implementation, evidence and limits](NATIVE_DANG_PREPARED_SCHEMA.md).

The following module-owner index screen changes ownership lookup from all-module scans to path-ancestor lookups. It remains unselected: complete test-edited listing moves **10.73 → 10.59 seconds**, faster in three of four pairs; ordinary-source listing stays **6.37 → 6.37 seconds**. Eight focused checks and all 24 timing commands pass. Both lossless profiles still execute 800 getters and reconstruct about **81 MB of receiver JSON**. Reconstructing all owner objects per package still scales with packages times modules. [Sources, all attempts and profiles](NATIVE_GO_MODULE_OWNER_INDEX.md).

These comparisons use real edits and fresh CLI processes on the same warm isolated engine within each study. Both arms finish adding and removing a test before measured pairs. The cohorts have different cache and engine states; their gains are not additive. Both ownership studies use the same engine after the earlier cancelled Rust fixture import and do not reset that cache. Only the development-check module gains the settings regression after the owner-facts timings and profiles; exact timed and final trees are retained and the main Go module source is unchanged.

First use with an empty Dagger cache was measured separately on an older stack: **20.19 seconds median from engine start through first listing**, across three independent engines. The image was already local and the host page cache was not flushed. That study does not establish cold performance for the current candidate or a retained-cache restart. [Cold-cache evidence](NATIVE_GO_COLD_LISTING.md).

Three seconds and a current Rust performance comparison remain unfinished.

The following [discovery screens](NATIVE_GO_DISCOVERY_PATH_WALKS.md) keep that pipeline intact. Header batching removes per-file reads but does not establish a useful test-edit gain. A single ownership walk improves ordinary-source listing **6.30 → 5.73 s** in all four pairs, with lower CPU and allocation. It remains experimental because the test-edit cohort encounters varying host CPU pressure and nearly flat engine CPU. The new ownership fixture also passes unchanged production code, preserving existing behavior for ignored names, nested boundaries and glob characters. No new latency claim is made for cold starts or Rust.

## Next targets

1. **Reduce repeated getter preparation where it costs time.** The edited listing still performs 804 module evaluations and 1,494 SDK requests. Its 640,000 repeated key-list entries account for only 0.16 sampled CPU-s in the motivating capture, so an extra conversion cache is not justified by the count alone. The callback-caller fix removes measured allocation scaffolding without changing callback-body execution. The parallel-admission retest stays unselected at **10.16 → 9.64 seconds** for test edits and **6.70 → 6.79 seconds** for ordinary edits. Attribute the remaining current-client, schema, configuration and resource preparation before proposing another shared context or cache. Preserve invalid-input errors, initializers, per-call state and freshness checks.
2. **Reduce shared package discovery.** Ordinary-source edits still take about six seconds even when getters and test discoveries hit. Earlier profiles place most of that command in `Go.packages`; improving getter setup alone cannot reach three seconds. Attribute current discovery CPU, allocations, serialization and SDK waits before changing algorithms or APIs. Previous marker batching, native sorting and smaller-owner screens did not establish sufficient full-command gains by themselves.
3. **Validate through execution.** For a candidate that improves complete-command time, repeat focused public-API checks for selection, failures, source overrides, module-boundary edits and restored versions. Verify native Rust compilation-action reuse and measure real edited builds separately. Expand race, resource, persistence and SDK coverage where the implementation changes those boundaries.
4. **Measure the remaining cold paths.** Compare first discovery on a new engine and discovery after a retained-cache restart. Keep image pulls and host-cache conditions explicit. Warm edited-listing measurements do not answer either question.

An initial three-second design budget is one second for discovery, one for collection expansion, and one for CLI startup, source import, output and cleanup together. These are targets, not measured phase durations or promised gains.

## Evidence for the structural direction

An explicit stored-item prototype reduces module evaluations **804 → 4** and test-edited listing **10.81 → 7.04 seconds**, faster in all four pairs, but regresses ordinary-source listing **6.00 → 6.52 seconds**. The author moves package construction into discovery, so this is a different execution shape. It establishes that repeated runtime preparation is expensive; it does not establish a way to skip existing getters. [Stored-item experiment](NATIVE_COLLECTION_STORED_ITEMS.md).

Sharing decoded JSON while rebuilding fresh invocation objects improves an 800-getter component **0.507 → 0.351 seconds**, but complete-command results are small and mixed. It stays disabled. Shared function metadata, global marker batching, smaller owners, parallel file reads and context-chain changes also failed to establish sufficient command-level gains. Preserve those results rather than repeating a component-only argument. [Improvement ledger and rejected screens](GO_COLLECTION_IMPROVEMENTS.md).

The selected native-source path already reduces 800 package existence queries to one snapshot walk. Content identity preserves 799 unchanged test discoveries when one package changes. These are normal Dagger snapshots and cache entries. The remaining work is chiefly shared discovery and repeated preparation around the still-required calls. [Snapshot discovery](NATIVE_GO_TEST_DIRECTORY_DISCOVERY.md), [getter identity](NATIVE_COLLECTION_GETTER_CONTENT.md).

## Acceptance

Run one structural experiment at a time. Use wcprof and CPU/allocation evidence to show which work changes, then compare balanced complete-command pairs without concurrent heavy work. Require correct ordered rows and successful exits, including cleanup. Preserve every attempt and restore source files, configuration and diagnostic switches.

Adding or removing a test must change exactly its row. Module-boundary edits must refresh ownership. Source overrides, overlays, subsets, reordered keys, deltas, object fields used as dimensions, selected execution and expected failures must retain their behavior. Cache reuse must follow current content and implementation identity, with session resources owned correctly.

Report total time, workload, warm/cold conditions, CPU, allocation and exact source/binary identities. Increasing package and module counts must show the intended scaling before calling an approach generally efficient. A component improvement is insufficient when the complete command stays flat; keep only changes whose gain justifies their complexity and risk.
