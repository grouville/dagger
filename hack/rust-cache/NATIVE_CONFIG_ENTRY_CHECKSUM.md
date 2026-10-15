# Validate Cargo configuration without copying it after every edit

The selected module validates its captured Cargo graph by filtering the source down to manifests, lockfiles, toolchain files and `.cargo` contents, then hashing that new directory. A large-workspace wcprof capture spends about 100 ms copying those files, another 20 ms committing the snapshot, and roughly 200 ms on the complete configuration request. An ordinary Rust edit invalidates the input directory even when all configuration files remain unchanged.

The experiment reads the selected native hash records directly. It requires an experimental engine API, [`Directory.digestEntries`](https://github.com/grouville/dagger/commit/b0820fb30), and a separate [Rust module change](https://github.com/grouville/dagger-rust/commit/3e8209e). The engine branch starts from selected prototype `6592f78d6`, with the existing measured overlays; it is not a standalone main-based upstream fix. No PR is open.

## Scope and correctness

The new checksum hashes each selected entry's full relative path, record type and existing metadata/content digest. Containing-directory headers are included; the receiver's own root header is excluded. A versioned prefix distinguishes this checksum from existing directory and wildcard-copy checksums. Full paths preserve the distinction between different tree structures containing the same basenames. Resolving a directory receiver follows its base symlink while child symlinks remain links. Existing checksum calls keep their behavior because the new `EntryPaths` option defaults to false. Imported records and their hash formats are not rewritten, and no shared state or locks are added.

The Rust module keeps its canonical configuration digest and its complete source-path check. The fast checksum is an additional guard stored in the native cache manifest, associated with that canonical digest. A matching guard avoids the filtered copy. A missing guard or mismatch still verifies the canonical filtered directory before deciding to recapture Cargo. This is necessary: the imported-source test found that a derived snapshot can rescan unchanged records in another hash representation. Treating every raw-checksum difference as a configuration edit caused false recaptures. The fallback restores the existing decisions and returns an updated guard for the next cache manifest.

The guard stays out of the captured compiler model. That model is an input to the Go program that launches rustc, whose executable digest is part of compiler-result identities. All tool inputs—`go.mod`, `go.sum`, `model/**`, `worker/**` and `cmd/**`—remain byte-identical to `28dab90`. The captured plan is unchanged when adopting a legacy cache; the new metadata is retained in its manifest. Existing compiled results and incremental seeds remain eligible for reuse.

Engine tests compare selected records against real filtered copies, including exclusions, empty directories, modes, scoped receivers, broken child symlinks and a base-directory symlink. Separate controls cover contents and metadata changes, tree structure, empty results, invalid patterns and invalid base paths. The complete contenthash package passes under race detection.

The module's native integration test compares plan decisions with the canonical implementation on both constructed and host-imported sources. It checks actual permissions after changing them, rather than assuming creation APIs overwrite existing modes. The cases cover ordinary source edits and permissions, manifests and containing directories, lockfiles, toolchain configuration, `.cargo`, path additions/removals and names containing spaces, brackets and exclamation marks. Legacy manifests without a guard are accepted after canonical verification. The replay suite, plan and incremental-compatibility checks pass under race detection; the compiler entrypoint compiles.

## Component and real-request measurements

On the same host, three runs of five iterations compare cached native records against the actual previous operation: a physical filtered copy followed by a normal directory checksum. The fixture contains 1,024 packages, each with a manifest and a Rust source file. Destination cleanup is excluded from timing.

| Operation | Median time | Allocated bytes | Allocations |
| --- | ---: | ---: | ---: |
| Filtered copy and legacy checksum | 145.32 ms | 52.60 MB | 276,148 |
| Selected native records | 5.23 ms | 0.956 MB | 32,997 |

An initial benchmark used the new entry traversal after copying; the final baseline was corrected to the actual legacy directory checksum before interpreting these figures.

Six fresh large-leaf command captures alternate the two modules on the same engine, separately from latency measurements. Every capture has zero dropped events and open operations. The three control configuration requests take **200.4, 196.8 and 202.6 ms**. The candidate requests take **6.2, 6.5 and 7.2 ms**, with no `Directory.filter` call: normal edited builds use the fast guard, without the canonical fallback. The candidate adds two requests while obtaining native directory IDs; its complete commands have 105 requests versus 103. Those requests are included in the command timings below.

## Complete edited commands

Both modules run on engine `16276`, with the same selected stack, primitive-array codec fix and new API. The control is module `28dab90`; the candidate is `3e8209e`. Both use the pinned Rust 1.77.2 toolchain and eight Cargo jobs. Telemetry is enabled, wcprof is disabled, and every command starts a fresh CLI after changing a used Rust value. Separate cache histories and source directories prevent one variant from populating the other's history. Two preparation rounds precede eight rotating pairs per scenario, with Cargo order also rotated.

Every launch first requires no active engine session and a one-second window below 5% host I/O stalls and 1% engine I/O stalls. Admission waits are recorded separately from command latency. No measured observation is discarded.

| First series | Control | Candidate | Cargo | Median paired saving | Candidate faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130-crate leaf | 0.715 s | 0.703 s | 0.130 s | 14.4 ms | 6/8 |
| 130-crate shared dependency | 1.380 s | 1.388 s | 0.635 s | 18.7 ms | 5/8 |
| 1,026-crate leaf | 2.068 s | 1.895 s | 0.817 s | 206.4 ms | 7/8 |
| Actual small collection tests | 1.060 s | 1.048 s | 0.511 s | 41.6 ms | 5/8 |

The crossover swaps modules between these histories without restarting the engine. It encounters substantial I/O pressure: 15 of 96 measured commands exceed 10% host stalls, with a 64.2% maximum. Large-leaf medians are 2.161 s versus 2.601 s, and small-collection medians 1.136 s versus 1.161 s. All observations remain in the data. This series does not establish a reliable improvement for the shared edit or small collection, and is not used as a clean large-workspace estimate.

A separate large-leaf confirmation uses a predeclared two-second quiet window with the same thresholds, one preparation round and eight rotating pairs. All observations are retained. Admission takes 80.05 seconds over 40 windows for 27 launches; one launch waits 28.04 seconds. During measured commands, host I/O stalls stay below 9.9% and engine stalls below 0.18%.

| Large-leaf confirmation | Control | Candidate | Cargo | Median paired saving | Candidate faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full edited command | 2.388 s | 2.245 s | 0.811 s | 154.8 ms | 8/8 |

The difference between column medians is 143 ms; 155 ms is the median of within-pair differences. Absolute command latency differs across series, so these gains must not be added to earlier medians from different runs. This measures isolated interactive-command latency, rather than sustained throughput. The Cargo-plus-0.5-second target remains unmet.

## Cache compatibility and remaining work

The final implementation accepts an existing 1,026-crate plan and cache, and the unchanged baseline worker still finds **1,026/1,026** results afterward. Final checks on both experiment histories retain 130/130, 1,026/1,026 and 6/6 results, with the expected preceding edit batches of 130, two and four actions. The engine update exits zero in 60.29 seconds and preserves the volume. No new correctness or lock regression was observed in these checks; general support for procedural macros and build scripts remains unfinished.

The [data and drivers](experiments/native-config-entry-checksum/measurements.json) preserve both complete cohorts, the confirmation, all pressure and admission records, corrected component runs, native decision tests, cache checks and complete profile summaries. The API's upstream design and hash-record portability still need broader validation before making this the official module's default. The remaining plan-read requests take roughly 69–138 ms in these captures despite only 1–3 ms in their file resolver, providing a separate next target.
