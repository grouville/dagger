# What improved real Go collection listing

The command remains `dagger check --module go --check test --list --all` on the real dagger/dagger checkout, returning 4,398 ordered rows. These are fresh CLI processes and real edits on a warm development engine. Telemetry, ordinary GC, successful session cleanup and final log flushing are included. This is an experimental engine, CLI and Go module together, not stock released Dagger.

The progression from roughly 40 seconds toward 12 seconds comes from engine/CLI changes, Go module changes and the embedded Dang interpreter. Each row below is its own controlled comparison; different source revisions, engine builds and cache states prevent treating the rows as a single additive waterfall.

| Improvement | Where | Complete-command comparison |
| --- | --- | --- |
| Read typed listing metadata in bulk and project immutable fields without per-field cache work | Engine + CLI | **40.86 → 26.76 s**, ordinary-source edits |
| Batch module paths and selection facts; retain discovered ownership | Go module + gomod | **25.45 → 19.21 s**, ordinary-source edits |
| Give package discovery native test-source snapshots and preserve content identity for unchanged getter results | Engine + Go module | **18.10 → 16.24 s**, test-file edits |
| Batch module validation and owned-file discovery | Go module + gomod | **17.35 → 15.92 s**, test-file edits; **10.39 → 7.56 s**, ordinary-source edits |
| Classify typed method declarations as functions instead of deferred variables | Dang interpreter | **14.31 → 12.71 s**, test-file edits |
| Read inherited source-error context only when evaluation fails | Dang interpreter | **12.88 → 11.51 s**, test-file edits; **6.67 → 5.75 s**, ordinary-source edits |
| Derive package test directories from one native snapshot walk | Go module | **12.22 → 11.25 s**, test-file edits; ordinary-source listing flat at **6.01 → 5.98 s** |

Evidence and scope: [typed metadata](NATIVE_TYPED_ARTIFACT_METADATA.md), [initial batched facts](NATIVE_GO_BATCHED_DISCOVERY_FACTS.md), [getter identity and snapshots](NATIVE_COLLECTION_GETTER_CONTENT.md), [batched package discovery](NATIVE_GO_BATCH_PACKAGE_DISCOVERY.md), [method classification](NATIVE_DANG_COERCED_METHOD_HOISTING.md), [error context](NATIVE_DANG_LAZY_ERROR_CONTEXT.md).

The [snapshot-directory follow-up](NATIVE_GO_TEST_DIRECTORY_DISCOVERY.md) removes 800 existence queries with one snapshot walk. All four test-edit pairs improve, with lower CPU and allocation in each. It leaves 804 module evaluations and uses linear membership in a 103-directory list. All 24 timing commands return correct rows and exit successfully; seven focused commands pass. This is a module-only follow-up on the experimental API, without an engine change or measured cold-start benefit.

The earlier **19.70 → 9.30 s** result belongs to the [first native-input prototype](NATIVE_GO_NATIVE_TEST_DISCOVERY.md), after an ordinary-source edit with unchanged test files. Test-file edits did not show that improvement. Later revisions refine this mechanism. It is not evidence of a ten-second cold start or a ten-second test-edit command.

The earlier roughly 100-to-40-second period was also not engine-only. Parallel Go discovery and retaining module ownership contributed alongside engine/runtime and host-file-walk improvements. The [historical report](NATIVE_GO_FULL_LISTING.md) preserves those comparisons and their limits.

## What is ready

The two final Dang fixes each reproduce independently on pristine upstream and pass its full interpreter race suite. Their minimal patches and review descriptions are prepared. No new PR is opened.

The combined listing prototype also passes real discovery, module-boundary and collection test-execution checks. The engine getter-identity change has focused cache/resource race coverage, and bulk metadata/projection has DagQL race and output-equivalence coverage. This does not establish universal compatibility across SDKs. The Go snapshot variant changes the direct discovery API; compatibility and a standalone upstream port remain work. The bulk metadata API requires the corresponding CLI and engine changes.

The latest shared-function-metadata experiment is not counted as another speedup: test-edited listing is **11.74 → 11.69 s**, faster in two of four pairs; ordinary-source listing is **5.96 → 6.25 s**, faster in one pair. It stays unselected. Its source-only protocol completes the test-layout transition in both arms before measured pairs, correcting an earlier first-pair confound. All 24 commands return correct rows and exit successfully.

A subsequent [cold-cache study](NATIVE_GO_COLD_LISTING.md) measures three independent new engines: **20.19 s median from engine start through first listing**, followed by **5.85 s** for ordinary-source edits and **12.27 s** for test additions. The image is already local and the host OS page cache is not flushed. All 12 commands succeed with correct rows. This is first use with an empty Dagger cache; a retained-cache restart is not measured.

Three seconds and integration of these collection changes into the Rust module remain unfinished.

The subsequent [native stored-item prototype](NATIVE_COLLECTION_STORED_ITEMS.md) establishes a larger structural gain: **10.81 → 7.04 s** after test edits, faster in all four pairs, with **804 → 4** module evaluations. It remains experimental because ordinary-source listing regresses **6.00 → 6.52 s**, and the new stored-getter form needs broader validation. SDK requests are essentially unchanged; the gain removes module setup. All 24 timing commands have correct rows and successful exits. Cold performance is unmeasured for this prototype.

A follow-up keeps the existing Go getter unchanged and shares decoded receiver JSON while constructing fresh invocation objects. The component improves **0.507 → 0.351 s** for 800 getters, but complete test-edited listing is only **10.91 → 10.61 s** (three of four pairs faster), with ordinary-source listing **6.06 → 6.18 s** (one pair faster). It remains disabled: the small, mixed complete-command result does not justify selecting a new process cache. Both lossless wcprof captures retain 804 evaluations and 1,494 SDK requests; all 24 timing commands are correct, the SDK race suite passes and six real module checks pass. This is evidence about preparation cost, not a completed getter-batching implementation or a cold result. [Full evidence and source](experiments/shared-receiver-decode/).

[Three subsequent setup screens](NATIVE_GO_DISCOVERY_SETUP_SCREENS.md) remain unselected: compact owners save allocation without a convincing latency gain, global marker batching removes searches without improving test-edited listing, and parallel test-file reads regress that workload. All 72 timing commands return correct rows and exit successfully. The independent [nested-list element type fix](NATIVE_DANG_NESTED_SELECTION_ELEMENTS.md) reproduces on pristine upstream and passes its race suite; it is a correctness fix, not another measured speedup.
