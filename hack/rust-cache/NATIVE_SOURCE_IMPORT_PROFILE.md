# Locate source-import cost after reducing plan reads

Two fresh edited commands in the 1,026-crate workspace spend **410 and 421 ms** importing their source directory. The existing `copy` spans account for **261 and 265 ms**; work before those spans takes **149 and 156 ms**. The `copy` phase includes the final checksum, snapshot lookup, physical copy, commit and metadata publication, so it is not a pure byte-copy measurement.

| Source size | Complete import | Before copy phase | Copy phase |
| --- | ---: | ---: | ---: |
| 1,026 crates, first edit | 410 ms | 149 ms | 261 ms |
| 1,026 crates, second edit | 421 ms | 156 ms | 265 ms |
| 130 crates, first edit | 62 ms | 29 ms | 33 ms |
| 130 crates, second edit | 59 ms | 27 ms | 32 ms |
| Small collection, first edit | 21 ms | 14 ms | 7 ms |
| Small collection, second edit | 10 ms | 8 ms | 2 ms |

These diagnostic captures use module `d565c70` and the same selected engine at port 16276. Every command has a new source edit, with native compiler results and incremental state already warm. Telemetry remains enabled. All six wcprof captures have zero dropped events and open operations. Span extraction reads only the new telemetry byte ranges; it deduplicates streaming updates by trace and span ID and uses completed records with valid end timestamps. Early summaries that included unfinished progress records are corrected in the archived analysis.

A separate 12-second CPU capture covers three large-workspace edits with wcprof disabled. It contains 6.58 seconds of engine CPU samples. The filesync call tree accounts for 0.87 seconds, and the broader `layercopy.Copier.Copy` tree for 1.00 second, including other directory-copy callers. File operations dominate those stacks. These are overlapping CPU totals, not elapsed savings or a timing comparison between implementations.

## Why a small edit still copies many files

`engine/filesync/localfs.go` starts each non-parent import with an empty mutable snapshot. The mirror synchronizes changed files, but both changed and unchanged selected entries enter the `only` set. If the complete imported digest already exists, the engine reuses that snapshot. A genuine edit changes the digest, so the engine copies the selected tree into a new immutable snapshot. Source hardlinks are disabled on this path: the mutable mirror must not change a previously imported directory.

This explains a substantial preparation cost without establishing a defect in hashing, locks or a particular library. A useful next experiment is to derive an import from a previous immutable snapshot and apply only differences. It must compare against that snapshot's actual records: a mirror can also have changed through other filters, concurrent imports or a failed import. Mirror change events alone are insufficient.

The experiment also needs bounded ancestry and retention, correct deletion and metadata handling, and a full-copy fallback. The [earlier compiler snapshot branching study](NATIVE_BATCH_COW.md) already shows that reduced copying can increase retained storage. Source import needs its own measurement and correctness evidence before selecting a similar tradeoff. The 261–265 ms phase is a target to investigate, not a promised command improvement.

[Archived diagnostics](experiments/native-source-import-profile/measurements.json) include completed source spans, telemetry offsets, wcprof summaries, the CPU profile and its reports, and the capture driver. No filesync behavior changes in this study.
