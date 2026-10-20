# Reuse declarations for identical current configuration

## Current draft: bounded LRU restored

[Draft #14741](https://github.com/dagger/dagger/pull/14741) again uses the small bounded LRU, keeping configuration parsing independent of engine session state. Its source and tests are identical to the previously verified LRU commit; component lookups measure **324.93 → 3.99 µs**, with a **4.7%** miss penalty. The earlier warm development-engine full listing improved **45.51 → 40.65 s** with only this cache toggled. That setup included other engine optimizations held constant.

**The current-main full-listing gain remains unverified.** New main, LRU and DagQL attempts all reach the 180-second limit without rows. They cannot establish completed-command performance or LRU superiority over DagQL. The PR stays draft. See the [cache comparison and full-repository screening](experiments/standalone-go-collections/assessment/config-cache-full-listing-oct19/).

## Why the current full listing remains slow

A [90-second wcprof/CPU diagnostic](experiments/standalone-go-collections/assessment/full-listing-gap-oct19/) still sits in package discovery, with no `GoPackage.tests` executions. The engine repeatedly loads Dang modules; sampled CPU includes 27.4% parsing and 37.3% background garbage collection. The CLI spends 80.2% of its sampled CPU walking directories. These are CPU-window measurements, not wall-time percentages or a new end-to-end benchmark.

The earlier ~45-second cohort also used the modified Go module, an experimental engine reusing eligible Dang module declarations, and a patched host-glob CLI. It was not only a different engine version. These differences identify larger work to investigate, but their individual contributions to the gap have not been measured on a fixed current-main setup.

## DagQL alternative, no longer the current PR

The DagQL version used `GetOrInitArbitrary`, replacing 49 lines of LRU helper with 40 lines and adding engine/session dependencies to the configuration package. Session-aware setup made the whole PR roughly the same size. Its repeated lookup result was **343.55 → 5.22 µs**, while distinct inputs cost about **13% more**. Its separate 16-package complete-command comparison **did not establish a gain**, 6.66 versus 6.83 s. Live snapshots verified use and release of the real configuration entry. These results remain in the [DagQL verification archive](experiments/standalone-go-collections/assessment/config-dagql-integration-oct19/).

The sections below retain the LRU measurements and their original benchmark conditions. Whole-command timings are from the earlier optimized development engine, not the new current-main attempts.

## Earlier LRU prototype


## Current-main verification, October 19

The independent patch now applies directly to main `ce6dc9f9403b52067f5831149eab4871f857185d`. Both main and the patch pass the complete workspace race suite with the same behavior tests. Four alternating fresh-process component pairs measure repeated lookups at **324.928 → 3.989 µs** and concurrent lookups at **139.608 → 1.178 µs**. Distinct content measures **335.409 → 351.0615 µs**, a 4.7% median miss penalty. Those fresh miss results supersede the older 1.5% estimate for the current patch. [Raw current-main verification](experiments/standalone-go-collections/assessment/config-declarations-oct19/) includes all checks, samples, logs and source hashes.

The full-command measurements below used an earlier experimental engine with the other changes held constant. They remain workload evidence, not a fresh measurement of this patch alone on current main.

The [cache-choice comparison](experiments/standalone-go-collections/assessment/config-cache-choice-oct19/) verifies that DagQL can also cache the parsed declarations. Lookup costs are similar; retain the small LRU for its explicit entry bound and configuration-only integration. This is not an end-to-end speed claim over DagQL.

## Earlier full-command investigation

Complete edited Go test listing improves **45.51 → 40.65 seconds median**, faster in all four pairs. Cumulative engine allocation falls **35.06 → 32.75 GB**, with engine CPU **218.89 → 206.55 CPU-seconds**. All ten commands, including initialization, return the expected ordered rows and exit successfully through session cleanup. Listing remains too slow.

The [host-read investigation](NATIVE_CONFIG_LOOKUP_COSTS.md) found 15,003 opens of the same unchanged configuration before module-function result lookup. The initialization comparison now counts **15,003 declaration lookups and one decode** in the candidate. The control performs 15,003 ordinary declaration loads. This change continues reading current bytes and checking the nearest configuration; it shares the derived declarations rather than repeatedly interpreting identical content.

The [standalone branch](https://github.com/grouville/dagger/tree/perf/reuse-git-client-declarations), commit `61db86655c2cd4e70a5a07dc6801034d0b41b4bd`, is based on upstream main `ff0b029a4d270a651b9a8c7286babc79089066e4`. Both affected existing files match the measured engine source exactly before patching. The patch adds a bounded in-memory cache of immutable declaration strings and warning messages, keyed by SHA-256 of the current bytes. It holds at most 32 entries and bypasses configurations larger than 64 KiB without rejecting them. Compiled results and Rust incremental state retain their existing native Dagger storage and identities.

Concurrent misses share one decode through `sync.OnceValue`. Parsing occurs outside the LRU mutex. Scope selection happens after each live read; each caller receives a copy of its declaration slice and warnings through its own telemetry context. A small helper separates configuration derivation from warning delivery. Invalid configurations still declare no clients, including their existing warning behavior. Read failures propagate before consulting this cache.

Three added behavior tests pass on the original and candidate implementations. They exercise edits, deletion, a nearer configuration with identical bytes but a different scope, corrupt and unreadable inputs, recovery, oversized configurations, caller mutation and concurrent readers. Separate caller log providers verify warning delivery, including warnings before a reconciliation error and their suppression on unknown-field errors. Full workspace race checks pass on the pure candidate, both actual-engine modes, and the standalone upstream-based branch.

Four alternating component pairs use the actual 1,649-byte Go module configuration:

| Case | Before | Candidate | Allocations per lookup |
| --- | ---: | ---: | ---: |
| Repeated content | 351.76 µs | 8.20 µs | 2,808 → 3 |
| Parallel repeated content | 137.24 µs | 1.11 µs | 2,808 → 3 |
| Distinct content in the combined benchmark | 307.47 µs | 408.54 µs | 2,813 → 2,814 |

The miss penalty is investigated rather than discarded. Four additional alternating, isolated fresh-process pairs with 5,000 distinct inputs each measure **308.26 → 313.03 µs**, about 1.5% slower. An independent CPU capture measures 300.39 → 306.49 µs and attributes 40 ms of 1.96 sampled CPU-seconds to SHA-256. These are different benchmark conditions; the initial combined-case penalty remains in the evidence. Real configuration misses gain no speedup.

The full command is `dagger check --module go --check test --list --all` on `dagger/dagger`. Both arms use one engine, CLI and module, fresh CLI processes and source edits, a warm retained engine, telemetry and ordinary GC. Direct built-in receivers, span indexing and sparse disk-usage sampling are common. Profiling and diagnostic counters are off during measured pairs.

| Pair | Decode each time | Share identical content |
| --- | ---: | ---: |
| 1, candidate first | 44.76 s | 41.12 s |
| 2, control first | 43.63 s | 39.68 s |
| 3, candidate first | 55.86 s | 40.18 s |
| 4, control first | 46.26 s | 41.78 s |

Every measured command returns identical 4,398 rows. The excluded initialization pair adds a real test, returns 4,399 rows and takes 45.95 → 39.17 s. Removing that test restores the expected listing. The median paired saving is 4.21 s; the difference between column medians is 4.86 s. The slowest control remains included; its recorded I/O pressure is low, with seven Go GC cycles versus five in its paired candidate. This does not establish what caused that individual delay. Savings must not be added to results from another cohort.

The owned engine restarts gracefully on its existing volume. All six native Rust histories retain every expected compiler hit before and on their first call after restart: 130/130, 1,026/1,026 and 6/6 on each side. The same checks pass after the listing cohort and profiling. Declaration reuse is now enabled on the development engine, with normal GC, profiling off and no active session.

A separate diagnostic completes in 45.65 s, with 570,464 wcprof events, zero dropped events and no open operations. Its 43.49-second main query attributes **32.53 s** to synchronous API intervals, **3.84 s** to dimension-key elements, **2.91 s** to artifact elements and **2.00 s** to publication. API intervals include engine processing and waits. Cumulative engine CPU includes **23.76 s** in Protobuf JSON serialization; CLI CPU includes **4.34 s** in the file service. These nested samples must not be added together. Sampled allocation profiles lag recent allocation and do not replace the command's cumulative counters.

The [host-request follow-up](NATIVE_CONFIG_HOST_REQUESTS.md) tests that next step. Reading first is rejected because it changes metadata-error handling and doubles missing-path probes. Combining stat and read preserves behavior and removes 15,003 requests, but its complete-command cohort regresses and stays unselected. Its diagnostic exposes a long cache-index compaction stall during publication. Existing direct Protobuf and callback-scope prototypes also need comparison on this workload before selection.

The [archive](experiments/config-content-declarations/) retains the pure patch, standalone validation, every benchmark attempt, fresh-input and warning checks, CPU captures, complete wcprof data, exact overlays and inherited source identities. The [PR description](PR_ENGINE_CONFIG_DECLARATIONS.md) accompanies [draft #14741](https://github.com/dagger/dagger/pull/14741), independently rebased and verified on current main. DCO passes.
