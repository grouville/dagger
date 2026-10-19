Parsing existing call JSON directly from its bytes reduces CPU and allocation on the large Go collection fixture, while complete-command latency improves only modestly. The variant remains **unselected** because it increases allocation for small object inputs. The full pipeline is preserved; no PR is opened or recommended for this version.

This is Go code in the engine's Dang SDK adapter, core/sdk/dang/v2. The Go and Rust modules keep their implementations. The adapter already receives receiver state and arguments as complete JSON byte slices, then copies them through encoding/json.Decoder's growing read buffer. The experiment uses github.com/segmentio/encoding/json.Parse, already present at v0.5.4 in Dagger's dependencies. It enables UseNumber and leaves all borrowed-string/number flags off. Each invocation still constructs fresh decoded values, converts private Dang objects, runs initializers and invokes the getter. No receiver cache, shared execution context or new engine API is added.

The helper preserves the existing single-value decoder behavior, including accepted trailing data. Numbers remain encoding/json.Number, including integers beyond float64 precision. If the alternative parser returns an error, the existing decoder supplies the established error type, offset and message. This is scoped to the two function-input decoding sites; streaming schema imports retain their existing reader. The dependency version is unchanged and becomes direct. The standalone production change adds a 22-line helper and replaces the two decoder blocks; the remaining source is tests and benchmarks.

| Complete warm listing after a real edit | Standard decoder | Direct parser | Faster pairs |
| --- | ---: | ---: | ---: |
| Ordinary Go source | 3.757 s | 3.671 s | 3/4 |
| Go test file | 6.017 s | 5.896 s | 3/4 |
| Test-edit engine CPU | 23.79 CPU-s | 22.91 CPU-s | 4/4 lower |
| Test-edit allocation | 5.351 GB | 5.143 GB | 4/4 lower |

Median paired test-edit savings are **90 ms and 206 MB**. One candidate pair is 218 ms slower, and it remains in the evidence. Source-edit CPU/allocation are mixed, with effectively flat resource use; its elapsed result does not establish a material gain. Host CPU pressure reaches 22% during test commands and 29% during source commands despite quieter admission. No samples are discarded.

Both arms use the same new engine, Go720 module, suffix-optimized CLI, COW class storage and immutable core field definitions. Only the JSON parser changes. Each workload completes two initialization blocks, adding and removing a real test, before four alternating measured pairs. All **24 timing commands** return exact ordered rows and exit successfully: 4,399 for addition initialization, then 4,398. Every command starts a fresh CLI and includes real source edits, telemetry, ordinary GC, final output and successful session cleanup. Profilers and diagnostic counters are off during timing. Caches are warm. These are development-stack results; current cold first use, retained-cache restart, released-engine and Rust latency effects are unmeasured. Do not add these medians to prior cohorts.

Four lossless comparative wcprof captures retain **800 authored getters, 804 module evaluations, 799 discovery hits and 1,415 SDK requests** in both modes, without dropped events or open operations. Each capture records 1,608 input decodes and 52,181,590 aggregate input bytes. The candidate routes those calls through the direct parser without retaining decoded receivers. Sampled call-decoding allocation falls from roughly **307/332 MB** to **132/132 MB**; total streaming-read-buffer samples fall **208/221 → 24/24 MB**. Samples can lag GC cycles and carry preceding-mode work, so exact per-command allocation counters remain authoritative. Profiled command times are diagnostic and separate from timing samples.

The component benchmark uses synthetic receivers with 1, 64 or 800 path strings and an exact-number field. Four alternating fresh-process pairs give:

| Paths in receiver | Standard → direct time | Standard → direct allocation |
| --- | ---: | ---: |
| 1 | 2.10 → 1.42 µs | 1,496 → 5,264 B |
| 64 | 14.99 → 8.79 µs | 7,696 → 10,216 B |
| 800 | 169.88 → 92.28 µs | 131,600 → 80,364 B |

Time improves in every component pair, but small objects allocate more. That tradeoff prevents a general speedup claim or unconditional selection. The next step is to establish the size/shape crossover and compare a justified strategy that avoids this penalty, then measure its full-command effect. A cutoff chosen only to make this fixture look better would not resolve the general concern.

Both the standalone pinned-upstream SDK race suite and exact experimental-engine SDK race suite pass. Differential fuzzing executes **266,289 cases** against the standard decoder across generic-value and receiver-map destinations; 268 interesting inputs are archived. Checks include exact numbers, duplicate keys, nulls, malformed JSON, trailing data, invalid UTF-8, surrogate escapes and nesting. Input-ownership checks mutate the source bytes after decoding. Negative controls removing UseNumber or enabling borrowed storage fail as expected. All 27 Go checks and 28 Rust/native-cache cases have expected outcomes, including actual selected execution, required failures, edited/restored source, settings/layout behavior and native compilation-action hits. Native Rust artifacts remain Dagger filesystem snapshots.

The source is [bd513bc5bc](https://github.com/grouville/dagger/commit/bd513bc5bc8067440a74d43921027096465ed70f), branch experiment/dang-json-buffer-decoding, based directly on pinned upstream 18d51f8291eabe93dc2b8e93dd47c8cfa6397625. The engine uses development base ff0b029a4d and SHA 67ca2c2c9d1639074bb9435850e447fbcb3f922ff101583ea782cabe4fb705fe. The common CLI remains ca716780a17686774e2df72e69f10116e41b1f195426f9eaa6f6f5bc35a2efe2. [Evidence](experiments/dang-json-buffer-decoding/) retains exact source, corpus, validation, component pairs, complete timings and four reconstructable profiles. The source branch is pushed to the fork for tracking, not submitted upstream. All nineteen engines and volumes are retained, with binary identities verified, flags/profilers restored, sources clean and no active requests or runtimes.

The leaf-allocation audit also ruled out misleading parent attribution: query parsing and sorted map iteration include substantial schema work underneath them. The previously tested smaller telemetry flush buffer remains unselected rather than being presented as a new fix. The broader target is still the full discovery → collection → selection → execution → cleanup pipeline at materially lower latency; this decoder experiment does not complete it.
