# Derive edited source imports from immutable snapshots

The [source-import profile](NATIVE_SOURCE_IMPORT_PROFILE.md) located about 260 ms in the large workspace's copy phase. The [prototype](https://github.com/grouville/dagger/commit/4c22cff4a) compares the current selected file records with a previous immutable import, then copies changed paths into a snapshot derived from that import. Rust compilation results and incremental state remain native Dagger snapshots; no compiler CacheVolume is introduced.

This is opt-in engine work based on experimental `b0820fb30`, not a standalone upstream patch or an official-module default. The benchmark engine also includes the separate [scoped-hardlink fix](SCOPED_IMPORT_HARDLINKS.md) in both comparison paths.

## Correctness and bounds

The hint index is scoped by the mirror snapshot, source path, copied subtree, include/exclude patterns, followed paths and gitignore setting. It compares actual records, because another projection or an unsuccessful import can change the mirror without publishing a snapshot for this selection. Cached maps are immutable after publication, and the index holds no snapshot leases. A collected parent falls back to a full copy.

The index holds at most eight selections and 65,536 records in total. A snapshot has at most eight derived parents; the next edit makes a new full copy. This first prototype also uses the full-copy path for removals, entry-type changes, hardlinks and special files. Regular files, directories, symlinks, metadata changes and re-included files beneath ignored parents are covered. The existing content-hash representation is unchanged.

The complete filesync package passes under race detection. Tests compare physical trees and imported digests against full copies in an independent snapshot store, including permissions, ownership, file timestamps and hardlink relationships. Nineteen serial edits check actual snapshot ancestry and the first snapshot's immutability. Further cases cover another filter changing the mirror, a failed commit, additions, deletions, type changes, links, garbage collection, concurrent imports and index bounds.

A public-API verifier passes twenty imports on the real overlayfs engine, both with the prototype enabled and disabled. It checks current and older contents, ignored/re-included files, symlinks, hardlinks, deletion and permissions. That check first exposed the independent scoped-hardlink bug; its failing baseline and fixed outcomes are retained separately.

## Component profiles

Separate diagnostic captures alternate full and derived copies on the same source histories. Every capture changes a source file; telemetry and wcprof are enabled. All twelve captures have zero dropped events and open operations. These profiles precede the hardlink fix, which does not change the ordinary-file fixture's records.

| Source import | Full-copy phase | Derived-copy phase | Full import | Derived import |
| --- | ---: | ---: | ---: | ---: |
| 1,026 crates, first comparison | 253 ms | 20 ms | 402 ms | 169 ms |
| 1,026 crates, second comparison | 263 ms | 20 ms | 412 ms | 169 ms |
| 130 crates, first comparison | 32 ms | 5 ms | 60 ms | 34 ms |
| 130 crates, second comparison | 38 ms | 4 ms | 70 ms | 34 ms |

The large import still spends about 149 ms before the copy phase. The small collection's copy phase takes about 1.3–1.5 ms with a full copy and 1.8–2.1 ms with a derived copy. Avoiding copies does not automatically benefit small trees.

## Complete edited commands

Both paths use module `d565c70` and engine `47af327f4`. A diagnostic overlay switches only snapshot-seed use on that one owned engine, outside timed commands; the committed prototype uses an environment flag and defaults to off. Every variant has a separate existing source and native cache history, with a fresh used Rust value per command. Cargo uses Rust 1.77.2, incremental compilation and eight jobs. Telemetry is enabled and wcprof disabled. Two preparation rounds precede eight rotating pairs per scenario.

Every launch first requires an idle engine and one second below 5% host I/O stalls and 1% engine stalls. All measured samples, periodic full copies and subsequent stalls remain in the data.

| First series | Full copy | Snapshot seed | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130-crate leaf | 0.680 s | 0.663 s | 0.130 s | 3 ms | 4/8 |
| 130-crate shared edit | 1.442 s | 1.390 s | 0.649 s | 45 ms | 5/8 |
| 1,026-crate leaf | 1.652 s | 1.426 s | 0.803 s | 194 ms | 7/8 |
| Actual small collection | 1.048 s | 1.058 s | 0.502 s | −21 ms | 3/8 |

The crossover swaps the implementations between the same histories without restarting the engine:

| Histories swapped | Full copy | Snapshot seed | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130-crate leaf | 0.675 s | 0.665 s | 0.131 s | 14 ms | 7/8 |
| 130-crate shared edit | 1.315 s | 1.358 s | 0.637 s | −8 ms | 4/8 |
| 1,026-crate leaf | 1.690 s | 1.437 s | 0.798 s | 191 ms | 8/8 |
| Small collection, seven completed pairs | 1.043 s | 1.028 s | 0.516 s | 5 ms | 4/7 |

The crossover does not complete: its eighth candidate collection command is cancelled after **484 seconds**. Goroutines show three Debian HTTP requests on the same HTTP/2 connection, rather than filesync or snapshot-copy work. The failed observation and diagnostic intervention are retained; the eighth baseline collection command never runs. The seven successful pairs are not presented as a complete collection result. The module's package discovery runs Cargo metadata through its fully prepared toolchain, including three checksum-pinned HTTP inputs, making that path a concrete next target.

Measured host I/O stalls peak at 46.0% in the first series and 19.7% in the crossover; engine stalls peak at 17.0% and 2.0%. These are warm interactive measurements with prospective admission, not cold-start or throughput results. The repeated large-workspace gain is supported by the component profiles and both histories. Small and shared-edit benefits remain unproven, and the Cargo-plus-0.5-second target remains unmet.

After cancellation, direct native compilation completes the two pending small-workspace edits without collection discovery. Final checks recover 130/130, 1,026/1,026 and 6/6 results on both histories, with the expected preceding batches. The hint index and parent chains are bounded in the tests; matched storage, restart and transfer measurements of this source-import variant are still required before selecting it. No PR is open.

[Data and drivers](experiments/native-source-import-snapshots/measurements.json) preserve both cohorts, the incomplete command, pressure and admission records, complete profile summaries, correctness checks and the diagnostic switch.
