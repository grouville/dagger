# Read artifact metadata without publishing each string

Complete edited 1,026-package listings improve in **15 of 16 pairs** when `Artifact.description` and `Artifact.uri` use the existing direct-field policy. Median paired saving is **328 ms**, with **368 MB fewer allocated bytes** per listing. The two-line production change is selected in the experimental engine and prepared as the ninth upstream proposal. Build/test controls show no established compilation gain.

## Target actual cache work

The listing's critical-path profile includes result publication, artifact metadata and array indexing. Some repeated `Artifact.items` and `ArtifactDimensionKey.dimensionKeys` entries are synthetic cached list-element lookups: they inherit their parent field name. They do not mean that the artifact resolver is re-executed for every row.

An initial attempt to make the dimension-key object list uncached fails its ID test: `ArtifactDimensionKey` elements become detached, so their IDs cannot be returned. That experiment is rejected. Artifact and key lists keep their existing cache policy and attachment behavior.

The selected change only marks the two string getters as `simple field selection`, following existing getter policy. Their strings derive from the retained artifact. It adds no cache, lock, API, dependency or persisted-format change.

## Complete commands

Both arms use the same diagnostic engine, physical source and native history. Every command has a fresh used source edit and CLI process, with warm engine/compiler caches. Telemetry stays enabled; Go GC and snapshot collection remain ordinary. Two independent balanced randomized orders are recorded with seeds 2026101608 and 2026101609.

| Edited 1,026-package listing | Before | Direct getters | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Initial eight pairs | 2.842 s | 2.604 s | 182 ms | 8/8 |
| Confirmation eight pairs | 2.823 s | 2.475 s | 380 ms | 7/8 |

Across both cohorts, the median paired saving is **328 ms**, allocated bytes fall by **368,448,992 per pair**, and engine CPU falls by about **1.00 CPU-second per pair**. Allocations are lower in 15/16 pairs. These values are paired differences, not differences between separately calculated column medians.

| Edited control | Median paired saving | Faster pairs |
| --- | ---: | ---: |
| 1,026-crate collection check | −6 ms | 8/16 |
| 130-crate direct check | −2 ms | 6/16 |
| Small collection tests | +2 ms | 8/16 |

The wide-check profile reads URI once and never reads description. No compilation speedup is claimed. Cargo controls, per-cohort medians, GC counts and all samples remain in the archive. These generated path-dependency workspaces do not establish registry, build-script or procedural-macro support.

All admitted observations are retained. Initial/confirmation timed-listing host I/O pressure peaks at **5.9%/3.3%**, with engine I/O below 0.2%. An isolated upstream worktree checkout occurred during confirmation and is recorded; direct-check host I/O reaches 23.1%. Initial quieter admission does not guarantee that pressure stays low throughout a command.

## Verify the work removed

Separate completed wcprof captures show exactly **2,052 fewer publications** in a full listing:

| Listing operation | Before | Direct getters |
| --- | ---: | ---: |
| Result publications | 7,518 | 5,466 |
| Description reads | 1,026 | 1,026 |
| URI reads | 1,026 | 1,026 |
| Artifact array-element lookups | 1,026 | 1,026 |
| Dimension-key array-element lookups | 3,078 | 3,078 |

Field reads and object attachment remain present. All four CPU/wcprof captures complete without dropped events or open operations. Instrumented timings are excluded from the cohorts.

Six fresh-process component pairs on the experimental engine improve 1,026-artifact metadata reads **76.4 → 31.6 ms**. A separate six-pair run directly on upstream main with the standalone patch repeats **76.3 → 31.6 ms**, with **37.0 → 26.1 MB allocated** and **467,821 → 304,245 allocations**. The single-artifact main case improves **219 → 148 µs**, with about 9 kB fewer allocated bytes. Fixtures are outside the timer, and each iteration reads a new parent generation.

## Correctness, selection and upstream branch

Focused artifact/core/schema race suites pass on both the experimental build and the standalone upstream patch. The compatibility test changes parent metadata across generations, checks the returned strings and loads artifact and dimension-key IDs. It would catch the detached-object failure from the rejected list policy. Existing artifact URI tests retain absolute-address and error coverage.

All six retained native histories pass strict reuse: 130/130, 1,026/1,026 and 6/6 compiler actions in each history. Preparation first compiles any last edit left by Cargo or listing controls. These unchanged commands are correctness checks only. Rust compiler outputs and incremental state remain native immutable snapshots.

The [standalone branch](https://github.com/grouville/dagger/tree/perf/upstream-artifact-metadata-fields), `e86fabff3ee6a91f2f20d56b3b159aacf9b8172a`, is based directly on upstream main `717589c9cc`. It is independent of the previous eight proposals. The [description](upstream-prs/artifact-metadata-fields.md) is ready for individual approval; no PR is open.

The selected diagnostic engine is now `ad2af24c…`, with both metadata strings and the existing dimension-key string getters direct. The module stays `da1ae47`, parallel fingerprinting stays off, and all other benchmark controls are unchanged. [SELECTED_BASELINE.json](SELECTED_BASELINE.json) records the source manifest and policies. The full Rust-cache goal remains incomplete.

[Archived evidence](experiments/artifact-metadata-fields/) contains both cohorts, raw pressure and edits, the component and main tests/benchmarks, profiles, source mirrors, the rejected list-ID reproduction and selected runtime state. Binaries, volumes, targets and Git metadata are excluded; local absolute paths need adapting to replay the drivers.
