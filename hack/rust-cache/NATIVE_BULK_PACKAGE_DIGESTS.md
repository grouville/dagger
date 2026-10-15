# Group native package hashes in one operation

The direct-path variant still makes one engine operation per package digest. The [experimental API](https://github.com/grouville/dagger/commit/6592f78d6) returns subdirectory hashes in input order through one `Directory.digests(paths:)` operation. Its resolver calls the existing single-path implementation, preserving modes, symlink handling, scoping and errors. The [Rust module variant](https://github.com/grouville/dagger-rust/commit/28dab90) groups packages without child exclusions; nested parent packages keep the existing removal recipe. Compilation arguments, workers, artifacts and source ownership are unchanged.

This requires another experimental engine API and remains isolated. The control module is `d098517`, which already hashes subpaths directly. Neither the selected module default nor an automatic size threshold changes. No upstream PR is open.

## Why the first grouping attempt failed

The first eight-pair series establishes no general command gain. A 1,026-crate leaf edit takes 5.187 s with individual hashes and 5.388 s with grouping; median paired saving is −225 ms. Host I/O stalls reach 74.2%, and native Cargo also has multi-second outliers. All four scenarios, pressure and samples remain in the data.

Fresh wcprof captures locate a separate implementation problem: the grouped resolver takes 52.38 ms, but publishing its string array takes 408.79 ms. The cache ownership walkers copy the entire input-path list for each output string. The [standalone fix on main](NATIVE_PRIMITIVE_ARRAY_OWNERS.md) removes this quadratic traversal for concrete primitive arrays. The next comparisons use that fix on the same engine for both module variants.

## Complete edited commands after the ownership fix

Both variants use one warm engine with the same content-keyed syntax cache and primitive-array response handling. Each has its own source tree and native history. Rust 1.77.2 uses eight compiler jobs. Every command follows a new, distinct source edit; order rotates with native Cargo. Telemetry remains enabled and wcprof is disabled. Timing uses blocking process exit without timeout polling. Two preparation rounds precede eight pairs per scenario, and no unrelated build or test runs during timing.

| First series | Individual hashes | Grouped hashes | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.744 s | 0.743 s | 0.097 s | −1 ms | 4/8 |
| 130 crates, shared edit | 1.410 s | 1.384 s | 0.616 s | 15 ms | 4/8 |
| 1,026 crates, leaf edit | 2.389 s | 2.258 s | 0.770 s | 65 ms | 5/8 |
| Actual package test collection | 1.039 s | 1.023 s | 0.483 s | 36 ms | 5/8 |

The implementations are swapped between those same histories without restarting the engine. Two preparation rounds precede eight more pairs:

| Histories swapped | Individual hashes | Grouped hashes | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf edit | 0.721 s | 0.701 s | 0.097 s | 34 ms | 5/8 |
| 130 crates, shared edit | 1.383 s | 1.359 s | 0.611 s | 1 ms | 4/8 |
| 1,026 crates, leaf edit | 2.325 s | 2.204 s | 0.761 s | 131 ms | 7/8 |
| Actual package test collection | 1.025 s | 0.998 s | 0.481 s | 14 ms | 6/8 |

Host I/O stalls reach 81.9% in the first series and 25.1% in the crossover; engine I/O stalls reach 47.8% and 7.0%. The first series retains grouped large-edit outliers of 12.599 s and 9.091 s. The crossover retains a 4.032 s grouped shared edit and 3.357 s control leaf edit. Column medians and within-pair savings are reported separately.

The large leaf benefit survives swapping histories. Other benefits are small or mixed. The large grouped median still exceeds Cargo by about 1.44 s, and the small collection remains about 0.52 s above Cargo. The Cargo +0.5 s target is not established. These results must not be added to medians from earlier experiments.

## Verify the mechanism and native reuse

The 1,026 individual hash operations become one grouped operation; two unrelated directory selections and 103 total engine requests remain in each large capture. With the ownership fix, the grouped resolver takes 55.44 ms and publication takes 0.63 ms. Its enclosing hash request takes 209.50 ms. The matching individual-path request takes 358.20 ms in the other capture. These diagnostic intervals locate work; they are not extra savings to add to the command medians.

The candidate capture also contains a separate 1.419 s Cargo-configuration filter request, including 1.178 s attaching a snapshot lease and 108 ms copying files. That request, rather than hashing or container startup, explains much of this capture's remaining delay. The archived critical path keeps these costs separate.

The engine integration passes under race detection for constructed and imported sources, file and directory modes, scoped parents, symlinks, input order, duplicate paths, empty input, missing paths and files. The old experimental base has an unrelated test compile error: a remaining `identity.NewID()` call without its import. A temporary test-only overlay uses the already imported `rand.Text()`; this workaround is absent from the API and standalone fix commits. The Rust package ownership integration also passes under race detection against the real engine.

A control-history bridge recovers 130/130 results before and after introducing grouping. A subsequent clean binary update exits zero in 11.76 s and retains 1,026/1,026 results. Switching between individual and grouped hashes recovers those same results. After the crossover, both histories recover 130/130 workspace results, 1,026/1,026 large results and 6/6 collection results. Their last shared, large-leaf and collection edits have exactly 130, two and four execution markers. Thus a slower sample is not treated as evidence of a cache miss without inspecting reuse.

The [measurements](experiments/native-bulk-package-digests/measurements.json) retain the naive series, both corrected series, pressure, complete profile summaries, I/O counters, clean-restart outcomes and correctness checks. Drivers, verification and critical-path reports are archived beside them. The engine API, Rust consumer and independent ownership fix are pushed on separate fork branches.
