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

Evidence and scope: [typed metadata](NATIVE_TYPED_ARTIFACT_METADATA.md), [initial batched facts](NATIVE_GO_BATCHED_DISCOVERY_FACTS.md), [getter identity and snapshots](NATIVE_COLLECTION_GETTER_CONTENT.md), [batched package discovery](NATIVE_GO_BATCH_PACKAGE_DISCOVERY.md), [method classification](NATIVE_DANG_COERCED_METHOD_HOISTING.md), [error context](NATIVE_DANG_LAZY_ERROR_CONTEXT.md).

The earlier **19.70 → 9.30 s** result belongs to the [first native-input prototype](NATIVE_GO_NATIVE_TEST_DISCOVERY.md), after an ordinary-source edit with unchanged test files. Test-file edits did not show that improvement. Later revisions refine this mechanism. It is not evidence of a ten-second cold start or a ten-second test-edit command.

The earlier roughly 100-to-40-second period was also not engine-only. Parallel Go discovery and retaining module ownership contributed alongside engine/runtime and host-file-walk improvements. The [historical report](NATIVE_GO_FULL_LISTING.md) preserves those comparisons and their limits.

## What is ready

The two final Dang fixes each reproduce independently on pristine upstream and pass its full interpreter race suite. Their minimal patches and review descriptions are prepared. No new PR is opened.

The combined listing prototype also passes real discovery, module-boundary and collection test-execution checks. The engine getter-identity change has focused cache/resource race coverage, and bulk metadata/projection has DagQL race and output-equivalence coverage. This does not establish universal compatibility across SDKs. The Go snapshot variant changes the direct discovery API; compatibility and a standalone upstream port remain work. The bulk metadata API requires the corresponding CLI and engine changes.

The latest shared-function-metadata experiment is not counted as another speedup: test-edited listing is **11.74 → 11.69 s**, faster in two of four pairs; ordinary-source listing is **5.96 → 6.25 s**, faster in one pair. It stays unselected. Its source-only protocol completes the test-layout transition in both arms before measured pairs, correcting an earlier first-pair confound. All 24 commands return correct rows and exit successfully.

A subsequent [cold-cache study](NATIVE_GO_COLD_LISTING.md) measures three independent new engines: **20.19 s median from engine start through first listing**, followed by **5.85 s** for ordinary-source edits and **12.27 s** for test additions. The image is already local and the host OS page cache is not flushed. All 12 commands succeed with correct rows. This is first use with an empty Dagger cache; a retained-cache restart is not measured.

Three seconds and integration of these collection changes into the Rust module remain unfinished.
