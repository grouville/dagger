# Upstream scalar-list rendering does not improve this Go listing

The latest complete Go collection listing takes **40.28 seconds median** with the selected implementation. Adopting the broader upstream scalar-list renderer measures **40.72 seconds**, slower in three of four pairs. It stays disabled in the retained diagnostic engine. This establishes no further improvement over the earlier, separately matched **42.24 → 35.90 second** data-list projection study.

`dagger check --module go --check test --list --all` runs on source `ff0b029a` with Go module `7568cd0`, CLI `e7ba08d0` and controlled engine `5f21c750`. Both arms keep the selected data-only object projection and other existing optimizations. Only the broader scalar-list renderer changes. Each invocation starts a fresh CLI and receives a fresh source comment on the same warm engine and volume. Telemetry and ordinary GC stay enabled; timing has no profiling. The local telemetry receiver does not model production Cloud latency. No cold-start time is established.

| Pair | Selected path | Upstream scalar-list path |
| --- | ---: | ---: |
| 1, candidate first | 37.06 s | 41.19 s |
| 2, control first | 43.50 s | 49.63 s |
| 3, candidate first | 60.94 s | 40.25 s |
| 4, control first | 36.98 s | 37.69 s |

All ten commands, including the excluded initialization pair, return the expected ordered rows and exit successfully through cleanup. Initialization adds a real test and finds 4,399 rows; measured pairs remove it and find 4,398. Median paired saving is **−2.42 seconds**. The third control coincides with class-slot count falling from 752,544 to 556,023; its 20.69-second gap cannot be attributed to scalar-list rendering. The other three pairs all favor the selected path. Every attempt remains included.

Column-median allocation is **29.94 → 30.18 GB**. Engine CPU is **192.94 → 190.43 CPU-seconds** at the column medians; concurrent CPU totals are not elapsed time and do not establish a reliable command gain. The candidate therefore offers no measured benefit for this workload.

## Why the component result was insufficient

The retained diagnostic engine already renders four typed scalar arrays without individual cache entries. [Alex Suraci's upstream change](https://github.com/dagger/dagger/commit/aacc932b7dcec8b95f74e6e445cfde582b00ee67), present in main `ff0b029a`, also handles plain dynamic and nullable arrays. This experiment ports that broader iteration strategy while preserving the retained engine's parent resource, released-session, cancellation and resource-growth checks. It is adoption of existing upstream work, not a new upstream proposal.

The component benchmark returns a dynamic array with an equally long list argument. The old path copies that argument for each result element. At 1,024 elements it measures **279.81 → 0.295 ms** and **637.02 → 0.341 MB** allocated per repeated-parent query. One element measures **22.03 → 15.85 μs**. Both sizes improve in all four alternating fresh-process pairs with ordinary GC. This deliberately exposes repeated argument copying; it does not establish that the real listing spends material time doing it.

The initial benchmark omitted its schema element type, then supplied variables in the wrong Go container type. Their source and failed logs are retained separately. Only the final corrected, smoke-checked binaries contribute measurements. The functional tests were unchanged by those fixture corrections.

The completed diagnostic capture finds the missing leverage: `String.dimensions` loses its **105** item publications, while the major glob and file-discovery call counts remain unchanged. It still publishes **7,507 search-result items**. The earlier data-only key projection remains active: its 17,592 synthetic item publications stay absent and both scalar getters still execute 17,592 times. The candidate removes little additional work from this listing.

The capture returns the correct rows and exits successfully in **36.00 seconds with profiling enabled**, recording **385,267 events, zero dropped and none open**. That single diagnostic run is not a new performance result. Its main query takes 34.30 seconds; **26.05 seconds** of its reconstructed critical path lies inside module API requests, including backend work. That is not a measurement of transport overhead or file parsing. The seven CPU windows sample 185.74 CPU-seconds across 36.15 seconds, including a tail after command completion. Background GC marking accounts for 38.40 cumulative CPU-seconds and protobuf JSON encoding for 20.72; those concurrent totals overlap other work and are not additional elapsed-time savings.

## Correctness and retained state

The selected control's focused race checks and the candidate's full DagQL race suite pass. Focused coverage verifies nullable and escaped values, reflected native arrays, explicit attached IDs, resource access, cancellation, released sessions and a resource requirement growing during iteration.

All six native Rust histories reuse every compilation action before replacement, on their first candidate-enabled calls afterward and after the complete cohort and profile: **130/130, 1,026/1,026 and 6/6**, twice each. The engine exits gracefully after **198.86 seconds** on its accumulated cache state; the replacement uses the same volume without a reset or forced termination. That shutdown duration is separate from listing cleanup. The primary Rust timing manifest is unchanged. The final retained state has the broader scalar-list switch disabled, data-only object projection enabled and global profiling off.

The archive retains exact overlays and source context, all component attempts, both full-command arms, output checks, native-cache checks, the restart captures and the subsequent wcprof/CPU capture. Local paths need adaptation for replay. No engine binary, cache volume, compiler target directory or credential is included. No PR is opened; the proposal count remains sixteen Dagger descriptions plus one Go-module description.

The [retained evidence](experiments/upstream-leaf-array-response/) records the negative result and selected state. The earlier [data-list projection study](NATIVE_COLLECTION_DATA_PROJECTION.md) has its own matched cohort and remains a separate result.
