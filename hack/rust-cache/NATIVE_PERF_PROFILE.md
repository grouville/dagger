# Profiles after sharing module schemas

The direct full-command comparison for 128 checks improves from 4.33 s to 2.30 s after the two check-execution fixes. Those checks read an edited workspace file; engines and module loading are warm. The same fixes have no established benefit for the small Rust collection, which batches its packages into one check. See [NATIVE_COLLECTIONS.md](NATIVE_COLLECTIONS.md) for the separate comparisons and correctness checks.

## Remaining measured work

| Workload | Evidence | Next experiment |
| --- | --- | --- |
| 128 checks after edits | Four commands in an eight-second engine CPU capture: decoding schemas consumes 9.40 CPU-seconds; encoding schemas for `SchemaForView` consumes 7.42 CPU-seconds, or 17% of all samples. | Lazy schema hashing is measured below. Schema decoding remains a separate opportunity. |
| Native Rust package collection after a code edit | wcprof records 11 helper arguments fetched through separate name, value and ID operations. Source import and module preparation precede compilation. | Batch argument retrieval into one query; inspect source preparation independently. |
| Native Rust tests in a 102-crate workspace | Fresh leaf and shared-library captures pass. The shared-edit diagnostic command takes 10.7 s and starts three Dagger execs. `Directory.directory` runs 103 times; result publication runs 750 times. | Inspect package-directory preparation and the native helper's graph construction, compilation and snapshot publication independently. |

The 102-crate shared-edit capture sums 9.6 ms of runtime startup across three execs. Starting hundreds of test containers is no longer the bottleneck after test batching. Directory synchronization sums 5.15 s across concurrent calls; that is not an additive contribution to command latency. Likewise, the three exec workloads sum 14.91 s during a 10.65 s engine-query window because helper work and other execs overlap.

The outer critical path attributes most Rust work to `dang.invoke`; the helper's nested API operations and compiler processes need their own analysis. Do not interpret this as 10 seconds spent executing Dang instructions. Worker timing records and nested operations are needed to separate those costs.

## Compute schema digests only when needed

`SchemaForView` serialized every prepared schema into JSON solely to compute its digest, including schemas used only to validate API requests. [bd6e3a55e](https://github.com/grouville/dagger/commit/bd6e3a55e) moves that work to `SchemaDigest`, retaining the same JSON encoding and XXH3 format. The digest remains cached and normal schema invalidation clears it. If an installation invalidates the schema before the digest acquires its lock, the getter rebuilds it rather than hashing a missing schema. The change adds no lock.

Focused race tests verify the exact encoded digest, different API views, concurrent readers, class changes, fork isolation and server lifetime. Eleven actual-engine integration cases pass, including edited workspace checks and evaluation after the discovering session closes.

Eight alternating full-command pairs, after warming both engines and module loading, improve the 128 edited checks from **1.897 s to 1.703 s**, with **193 ms median paired saving** and seven of eight pairs faster. Telemetry stays enabled and wcprof is off during timing. CPU/I/O pressure reaches 29.0%/1.1%. This comparison isolates the new digest change; do not add its medians to results from earlier measurement periods.

Each fixed eight-second CPU capture accompanies four edited commands. Schema encoding falls from **7.42 to 0.08 CPU-seconds**, while schema decoding records 9.40 versus 9.74 CPU-seconds. The windows are time-bounded and can omit command tails; they also include concurrent cleanup. They identify the removed encoding work rather than establish matched per-command CPU savings. The unprofiled pairs above establish the latency benefit.

A focused benchmark constructs a new fork and its schema with 1,024 fields on every iteration: median time falls from **2.081 ms to 0.311 ms** across three samples. Code and input data are warm; each schema is prepared from scratch. A repeated series uses idle research engines and no other build or benchmark.

The small native Rust collection again has no established gain: medians are 1.201 and 1.212 s, with four of eight candidate runs faster and 10.8 ms median paired saving. All samples are retained, including a 6.59 s control outlier. This standalone engine fix is pushed to the fork; no PR is open and it is not selected as a demonstrated Rust speedup.

## Batch helper arguments: fewer requests, no measured command gain

The Rust compiler helper uses an older Go SDK dispatch path that fetches function metadata and every argument separately. A local experiment fetches that dispatch input in one query. The actual edited collection capture reduces the helper client's requests from 75 to 50, and all engine requests from 118 to 93. The 11 arguments still resolve individually inside the combined query.

Eight alternating edited-build pairs, using the same engine for both module versions, give medians of **1.087 s before and 1.096 s after**, versus **0.489 s for Cargo**. Only three of eight candidate runs are faster; median paired saving is **−52 ms**. Reducing requests alone has not demonstrated a latency benefit, so this remains an unselected experiment. The later diagnostic capture includes a long candidate stall and is used only to verify request counts. The current Go SDK v2 already passes dispatch input directly; this observation is specific to the experimental helper's older SDK.

A separate capture with a CLI built from upstream revision `4e1042289` confirms that its two `Query.currentWorkspace` operations belong to the same outer client. The beta CLI capture has the same shape. The other clients are nested module invocations; these records do not establish duplicate CLI discovery and execution sessions. Both CLIs make 118 engine requests for the original helper. An earlier interpretation of the phase counts as two CLI sessions was incorrect.

## Reuse decoded schemas

With eager schema hashing removed, schema JSON decoding still consumes 9.74 CPU-seconds in the eight-second, four-command check capture. On the actual 592 kB exported schema, a typed independent copy plus SHA-256 over the input takes **2.16 ms**, versus **10.49 ms** for standard decoding, across three samples. Allocations fall from 3.14 MB to 0.52 MB per operation. This microbenchmark excludes reading the schema file and does not establish a command speedup.

The [standalone candidate d34e57548](https://github.com/grouville/dagger/commit/d34e57548) keys reuse by the actual input bytes, retains at most eight schemas with at most 1 MiB of JSON each, and returns independent copies because Dang mutates schema fields and directives. It retains no client, query or filesystem handles. Larger inputs bypass retention. Concurrent first use decodes once; decode errors are not retained. It adds no dependency.

Eight alternating full-command pairs improve the 128 edited checks from **2.032 s to 1.566 s**, with **429 ms median paired saving** and seven of eight pairs faster. Engines and module loading are warm; every command edits `application.rs`. Telemetry stays enabled and wcprof is off. Maximum CPU/I/O pressure is 38.9%/5.3%. These medians belong to a separate measurement period and must not be added to earlier savings.

A crossover swaps the binaries between those same cache volumes, warms module loading again, and repeats eight alternating pairs. The gain follows the code: **1.694 s to 1.442 s**, **238 ms median paired saving**, eight of eight pairs faster. Keep all samples, including the pair with 31.8% I/O pressure; maximum CPU pressure is 28.0%. The two series establish a benefit for this workload, with variable magnitude.

Focused race tests cover nested mutation, concurrent first use, changed schemas, eviction, oversized inputs and errors. Eleven actual-engine cases pass for workspace scope, edited failures, restoration, closed discovery sessions and returned check types; four existing self-call cases also pass. The branch is pushed to the fork, with no PR.

A representative 1,024-field benchmark includes reading the input into the cache: **9.67 ms to 2.04 ms**, with **1.80 MB to 1.58 MB** allocated. This is distinct from the actual-schema copy-only benchmark above; including the input read reduces the allocation benefit. Separate wcprof captures retain all 128 Dang invocations and 1,160 `Query.typeDef` calls. Summed schema-decode intervals fall from 11.55 s to 3.39 s across concurrent calls; those sums are not command-latency savings.

The real small Rust collection shows only a modest signal: **1.130 s to 1.120 s**, Cargo **0.496 s**, six of eight candidate runs faster, and **35 ms median paired saving**. This series does not establish a general Rust speedup or meet the Cargo-plus-0.5-second target.

After this change, a 1.38 s diagnostic check capture attributes **464 ms** of its critical path to source preparation and **232 ms** to opening the schema file. The schema's actual decode/copy contributes about 3 ms on that path. Source mounting and schema-file opening are the next concrete targets; these intervals do not prove they can all be removed.

## Separate foreground work from cache cleanup

A fresh shared edit in the 102-crate test fixture passes in **10.76 s**. A two-second CPU window lies entirely inside that command, with no session cleanup active before it starts. It records **1.71 CPU-seconds**: telemetry export includes 350 ms, protobuf JSON decoding includes 260 ms, and filesystem copying includes 250 ms. These are overlapping call-tree totals, not additive delays, and compiler processes outside the engine are not in its CPU profile. No session-pruning samples appear in that window.

The five-second capture immediately after the command records no engine CPU samples. The earlier 30-second profile's large prune cost is therefore not a fixed per-command charge. Cleanup timing depends on its trigger and throttle. These captures do not establish a benefit from changing or disabling cleanup, so it remains unchanged. The foreground sample covers only the first two seconds; later work inside the command still needs attribution.

The earlier wcprof capture places the three actual exec workloads on a timeline: the compiler helper runs for 5.64 s and includes a 4.67 s compiler worker; the following test batch runs for 4.60 s. Subtracting that contained worker interval leaves about 0.96 s of helper time outside the worker, including preparation and nested API requests. The broad `dang.invoke` interval therefore does not represent ten seconds of Dang computation. Test-process execution remains a major target alongside helper preparation.

The [Rustdoc follow-up](NATIVE_RUSTDOC_PATH.md) finds and fixes repeated toolchain selection in those test processes. The same 203-command test batch falls from 4.53 s to 1.89 s in a controlled comparison. Fresh-edit wcprof captures preserve the compiler work and three-exec structure. The small module's direct CLI median reaches Cargo +0.49 s, with a narrow margin; the larger full-command series remains too variable to establish its remaining gap reliably.

The [compiler-phase follow-up](NATIVE_COMPILER_PHASES.md) distinguishes the Dang module, its Go compiler submodule and the Go execution program inside the Rust container. Finer timers locate roughly 57–61 ms in retained-plan loading/decoding and 41–49 ms in package hashing in two many-crate leaf captures. Smaller dependency descriptions and reuse of the evaluated batch root both remain isolated: fewer transferred bytes or repeated recipes have not yet established a repeatable complete-command gain. Host and engine pressure are now recorded separately for the check comparison.

## Capture limits

Timing comparisons keep telemetry enabled and disable wcprof. Profiling captures are diagnostic runs, not replacement benchmark samples. No unrelated build, test or benchmark runs concurrently with the recorded workload.

The eight-second check profile includes overlapping cleanup from its four commands. The 30-second many-crate CPU profiles also include work after the CLI returns: in the shared-edit capture, `gcAfterSessionCompletion` and cache pruning account for 8.72 CPU-seconds, roughly half of the engine samples. This is a candidate source of contention for a following command, not proof that pruning added 8.72 seconds to the measured command. It needs an active-request capture and a separate cleanup measurement before proposing a change.

Raw artifacts live under `/tmp/rust-cache-sipsma-review`: `nested-schema-forks-cpu`, `rust-nested-schema-forks-profile`, `native-stack-many-oct14-profile`, `lazy-schema-digest-paired`, `rust-lazy-schema-digest-paired`, `lazy-schema-digest-cpu`, `lazy-schema-digest-micro-*-idle.log`, `native-helper-batched-{paired,profile}`, `current-upstream-cli-profile`, `dang-decoded-schema-{paired,crossover,profile}`, `rust-dang-decoded-schema-paired`, and `native-stack-foreground-cleanup`. The separate `dang-decoded-schema-cpu` attempt failed its window check: its fourth command finished after the CPU capture ended, so it is excluded from matched CPU comparisons. wcprof captures check for dropped events and unfinished operations. The collection fixture generator can reproduce discovery alone or actual checks that read a changed workspace file.
