# Encode primitive arrays without repeatedly copying their inputs

The real large-workspace profile exposed another quadratic copy after the ownership fix. Capturing cache evidence calls the persistence encoder. For each value in an `Array[String]`, that encoder calls `NthValue`, which copies the complete producer call twice. A call with 1,024 input paths returning 1,024 digests therefore copies roughly a million input arguments. This is on the active engine path: allocation stacks lead from `core.recordCacheEvidence` through `DefaultPersistedSelfCodec.EncodeResult` to `Array[String].NthValue` and `ResultCallLiteral.cloneWith`.

The [standalone fix](https://github.com/grouville/dagger/commit/725142070) starts at main `5d313bf2e`. It writes scalar envelopes directly for the exact Go types `Array[String]`, `Array[Int]`, `Array[Float]` and `Array[Boolean]`. Those arrays contain raw values with no separately attached identities or snapshot owners. Their persisted envelopes and scalar JSON stay identical. The list's authoritative declaration is still checked first. Other enumerables keep their existing encoding path. The change adds no shared state or synchronization and does not change the persistence format version.

## Component result

The benchmark has matching input and output list sizes. Three runs use ten iterations each on the same host, with eight Go workers.

| Elements | Main time | Fixed time | Main allocation | Fixed allocation |
| --- | ---: | ---: | ---: | ---: |
| 128 | 3.16 ms | 0.092 ms | 6.93 MB | 36.0 kB |
| 512 | 46.01 ms | 0.295 ms | 107.05 MB | 139.8 kB |
| 1,024 | 185.74 ms | 0.498 ms | 424.98 MB | 279.0 kB |

At 1,024 elements, allocations fall from 2,124,067 to 4,103 per operation. Doubling the old list from 512 to 1,024 multiplies allocation by 3.97 and time by 4.04. The fixed allocation grows by 2.00.

This is a performance change. The new compatibility test passes before and after: a wrapper forces the original generic Enumerable path and serves as an independent encoding oracle. Equality covers the scalar JSON bytes, types, identities, resource links and errors for all four primitive types, empty arrays, Unicode and escaping, exact large integers, negative zero, NaN and infinity. Focused race tests also pass for the existing custom-scalar, nested-list, object-list, attached-null, reference-relocation, second-save and restart cases.

## Complete commands after real edits

The control engine includes grouped package hashing, the primitive ownership fix, content-key syntax caching, the literal formatter and the disabled lease-phase diagnostic overlay. The candidate adds only this encoder change. Both use Rust module `28dab90`, the same pinned Rust 1.77.2 toolchain, eight Cargo jobs and native compiler snapshots. Existing source and cache histories from the formatter experiment are deliberately reused.

Every command changes a used Rust value, starts a fresh CLI and keeps telemetry enabled. wcprof is disabled for timing. Two fresh-edit preparation rounds precede eight rotating pairs per scenario. Medians from the first series are:

| Edited command | Control | Fixed | Cargo | Median paired saving | Fixed faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130-crate leaf | 0.697 s | 0.693 s | 0.097 s | 0.9 ms | 4/8 |
| 130-crate shared dependency | 1.369 s | 1.319 s | 0.608 s | 42.5 ms | 6/8 |
| 1,026-crate leaf | 2.213 s | 2.017 s | 0.757 s | 218.2 ms | 6/8 |
| Actual small collection tests | 1.007 s | 1.013 s | 0.486 s | −10.9 ms | 3/8 |

The uncapped crossover swaps binaries between the same owned engines, preserving both volumes through clean shutdowns. It encounters heavy I/O pressure: host stalls reach 79.8%, and 36 of 96 measured commands exceed 10% host I/O stalls. Cargo reaches 4.55 s and a Dagger command reaches 15.06 s. Small and shared scenarios become slower for the candidate. All samples are retained; that series does not provide a clean estimate of the encoder's command-level effect.

A separate, predeclared large-leaf confirmation keeps the swapped binaries and waits before each launch for both engines to finish sessions and for a two-second window below 5% host I/O stalls and 1% I/O stalls on either engine. Admission happens before timing; no measured observation is discarded. One preparation round precedes eight rotating pairs. All 27 launches meet admission on their first window; the 54.05 seconds spent in those windows are recorded separately. This measures isolated interactive-command latency, rather than back-to-back throughput.

| Large-leaf confirmation | Control | Fixed | Cargo | Median paired saving | Fixed faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full edited command | 2.203 s | 2.021 s | 0.794 s | 211.2 ms | 8/8 |

Host I/O stalls during those measured commands stay below 7.4%; neither engine exceeds 1.3%. The difference between column medians is 182 ms; 211 ms is the median of the eight within-pair differences. These are different statistics. The full command still takes Cargo plus 1.23 s, so the Cargo-plus-0.5-second target remains unmet. No improvement is established for the small collection.

## Confirm the removed work in the engine

Two fresh large-leaf wcprof captures per engine are separate from the timing series. All four have zero dropped events and open operations. Both CPU windows cover every command, with host I/O stalls below 2.9%. The grouped-hash request takes 197.4 and 189.8 ms on the control, versus 58.6 and 63.6 ms with the fix. Its resolver remains in the same 52–58 ms range. The removed time is outside the actual filesystem-hash resolver, consistent with the persistence-encoding allocation stacks.

Corresponding allocation profiles attribute about 375 MB to `ResultCallLiteral.cloneWith` on the control and 2 MB on the fixed engine. These are sampled allocation windows including background engine work, not peak memory measurements or an exact per-command allocation count.

After installing the fix, the existing 1,026 compiled results remain reusable. Final checks on both engines retain 130/130, 1,026/1,026 and 6/6 results, with preceding edit batches of 130, two and four actions. All three engine updates exit zero and preserve their volumes. No PR is open.

The [data and reproduction drivers](experiments/primitive-array-codec/measurements.json) retain all component runs, both uncapped command series, the idle confirmation, pressure and admission records, profile summaries and indexes, clean shutdowns and native-cache checks. The remaining repeated costs include the roughly 200 ms configuration filter and the large plan's request and decoding work; neither is changed here.
