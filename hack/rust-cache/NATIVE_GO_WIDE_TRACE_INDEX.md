# Avoid quadratic trace indexing during full Go test listing

The existing [span-index fix](NATIVE_SPAN_LOOKUP_FANOUT.md) improves full `dagger/dagger` listing **53.58 → 46.72 seconds** across three successful paired comparisons. Median paired saving is **7.05 seconds**. All four measured optimized commands succeed; one control times out during session shutdown. Every attempt returns the same 4,398 rows. Listing remains too slow.

This is the previously prepared fix, with no new production changes. The original `spanLookup.addLocked` function matches main checkout `ff0b029a` exactly. It scans a parent's children to reject duplicates. The fix skips that scan for new IDs using the existing parent map, retaining the fallback for cross-trace collisions. Cause links use their existing reverse index. No map, lock or retained state is added.

| Pair | Original | Optimized | Exit, original / optimized |
| --- | ---: | ---: | --- |
| Initialization, excluded; 4,399 rows | 51.82 s | 44.79 s | 0 / 0 |
| 1, optimized first | 49.69 s | 46.24 s | **1** / 0 |
| 2, original first | 49.93 s | 42.15 s | 0 / 0 |
| 3, optimized first | 53.58 s | 47.26 s | 0 / 0 |
| 4, original first | 53.77 s | 46.72 s | 0 / 0 |

Only pairs 2–4 enter successful latency statistics; all improve. Each arm uses a fresh CLI and source edit on the same warm engine, module `7568cd0`, selected literal-path CLI, ordinary GC and telemetry. The initialization pair adds a real test; measured pairs remove it. Profiling and counters are disabled during timing. Lazy type-map initialization is disabled in both arms.

Across successful pairs, median engine CPU is 235.18 → 234.06 CPU-seconds, cumulative allocation 36.32 → 37.19 GB and sampled peak heap 11.36 → 12.48 GB. These observations establish no memory or substantial overall CPU saving. Host IO pressure reaches 12.2% in the last control versus 0.5% in its candidate; the low-IO second pair still saves 7.78 seconds. Host CPU pressure spans 18.3–25.6%. The measured magnitude is specific to this setup.

The counted initialization control indexes 270,428 span snapshots and performs **2,021,168,795** ordinary-child comparisons for new IDs. The optimized initialization indexes 291,085 snapshots while avoiding **2,507,008,127** corresponding comparisons. These are separate live traces; their snapshot counts need not match. The index starts fresh for each session.

An eager-constructor diagnostic captures shutdown waiting in trace `ForceFlush` while its worker runs the original scan. Fixed-window CPU samples attribute 4.74 CPU-seconds to that function; the optimized diagnostic attributes 0.12 to its replacement. These windows cover different phases, so this demonstrates the mechanism rather than a matched full-command CPU saving. The optimized capture exits zero, returns 4,398 rows, and records 559,114 wcprof events with none dropped or open. It still makes 963 SDK invocations and 170,551 recorded calls; package discovery takes 20.76 seconds. Its profiled 51.95-second duration is outside the timing cohort.

The [standalone branch](https://github.com/grouville/dagger/tree/perf/upstream-span-lookup-fanout), `330c7d6`, and its compatibility/race tests are unchanged. Earlier small Rust results remain mixed. No PR is open.

Both arms use engine `afee1288dac6520523496d5f18e0443a1dd48cd1c08515c946d414333d8bffe8` and CLI `e7ba08d0e40f6a46ad3eb8df7397bd6827aa348f491a9cb9a726ff705e1fb122`. [Complete evidence](experiments/go-wide-trace-index/); [constructor candidate and interrupted cohort](NATIVE_DANG_TYPE_MAPS.md).
