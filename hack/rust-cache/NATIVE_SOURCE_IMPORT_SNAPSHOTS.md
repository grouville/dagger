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

After cancellation, direct native compilation completes the two pending small-workspace edits without collection discovery. Final checks recover 130/130, 1,026/1,026 and 6/6 results on both histories, with the expected preceding batches. The hint index and parent chains are bounded in the tests. The follow-up below measures physical storage and checks transfer correctness on the current engine; remote transfer latency remains unmeasured. No PR is open.

[Data and drivers](experiments/native-source-import-snapshots/measurements.json) preserve both cohorts, the incomplete command, pressure and admission records, complete profile summaries, correctness checks and the diagnostic switch.

## Verification on the current experimental engine

The follow-up uses the cumulative engine with compact scalar restoration enabled, module `cd6d25e`, and the buffered artifact-list CLI. Batch telemetry metadata and the attribute-array decoder are enabled in both arms. Source seeds are the only option switched between commands. Both Dagger arms use the same physical source directory and compiler-cache history; every command makes a fresh used source edit. Telemetry stays enabled and wcprof stays disabled during timing. These are warm edited commands, not cold builds or unchanged replays.

After two preparation rounds, eight rotating comparisons give:

| Command | Full copy | Snapshot seed | Native Cargo | Faster seed observations |
| --- | ---: | ---: | ---: | ---: |
| 1,026-crate leaf edit | 2.130 s | 1.924 s | 0.839 s | 5/8 |
| Small Rust test collection | 1.088 s | 1.040 s | 0.531 s | 6/8 |

All observations remain in the results. Median paired savings are 296 ms and 16 ms respectively; these differ from subtracting the column medians. The seeded large-workspace commands include 2.94 s, 2.64 s and 5.05 s observations. Host I/O stalls reach 54.3%, and engine stalls reach 15.3%, despite quiet admission before each command. The large-workspace result supports further work on this option; it does not establish a general or tail-latency improvement. The Cargo-plus-0.5-second target remains unmet.

Four separate wcprof captures have no dropped events or open operations. The large source import takes 711/437 ms with full copies and 189/202 ms with seeds. One seeded command still takes 4.36 s: its import stays at 202 ms, while check execution takes 3.11 s and package discovery takes 707 ms. A nested `withExec.applyOutputs` operation takes 1.08 s. These timings locate further work in execution and snapshot publication; `dang.invoke` includes helper execution and engine requests and must not be read as interpreter CPU time.

### Physical storage

A separate public-API verifier imports 19 fresh versions of the real 1,026-crate source tree per arm. Distinct marker files prevent content-hash lookup from reusing the other arm's snapshots. Both sessions keep the results owned until inspection. A brief pause of the owned engine makes the snapshot metadata copy consistent; the engine is unpaused before measuring the actual overlay directories with `du`.

| Retained sources | Full copy | Snapshot seed |
| --- | ---: | ---: |
| All 19 versions | 309.1 MiB | 49.1 MiB |
| Latest version, immediately before a reset | 16.27 MiB | 16.39 MiB |
| Latest version, immediately after a reset | 16.27 MiB | 16.27 MiB |

Physical and recorded sizes agree. Actual ancestry follows depths `0..8, 0..8, 0`: three full copies and sixteen small changes instead of nineteen full copies. Retaining the latest version immediately before a reset costs 128 KiB more than its full-copy counterpart. These are measurements of imported sources, not total engine or compiler-cache storage.

### Transfer and cleanup

[The added test](https://github.com/grouville/dagger/commit/19eda9248) exports a real derived snapshot chain and imports it into independent native snapshot stores, with and without an existing prefix. It compares complete physical trees, including file permissions and timestamps. A consumer that already has the base reads only the new layer. On this test fixture, uncompressed layer sizes are 625,664 bytes for the base, 628,224 bytes for the edited cold transfer, and 2,560 bytes for the warm transfer. This is a correctness and transfer-size test, not a remote latency benchmark.

The test reopens both snapshot managers, discards the source hint index, checks the durable snapshots after garbage collection, and checks that the next edit falls back to a full copy. After releasing their owners, every producer snapshot is collected despite the hint. The full filesync package passes under race detection in 13.398 s. The store uses native snapshots and real tar/apply operations without mount syscalls; the separate storage check exercises actual overlayfs imports.

With source seeds enabled, the six existing Rust histories recover every compiled result before and after a clean restart of the actual overlayfs engine: 130/130, 1,026/1,026 and 6/6 on both histories. The same binary and volume are retained, while the process-local seed index starts empty. The engine exits successfully and receives no forced-stop deadline. This verifies compilation reuse after a real process restart; it does not measure restart performance or automatic remote cache discovery.

The test and prototype are pushed on the fork; no PR is open. [Current evidence and drivers](experiments/native-source-import-snapshots-current/provenance.json) include all command samples, pressure records, four profiles, selected snapshot metadata, physical sizes, source and test logs. The initial storage harness closed its sessions before inspection, so its `noCache` results had already been released; the corrected harness keeps the owners alive until measurement.
