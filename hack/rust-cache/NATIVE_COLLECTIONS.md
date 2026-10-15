# Collections, check execution and module loading

Package selection belongs inside the Rust module. Its discovery and execution must share work across selected packages. The first collection prototype preserves Cargo's package selection and feature unification, but adds 174 ms in eight paired small-workspace edits. It remains experimental. Root workspace tests and collection tests also need a deliberate default selection before both can be enabled together.

## Index collection ancestors

`Artifacts.ForDimensionKeys` compared every artifact with every other artifact and rebuilt its dimensions for each comparison. A temporary prefix index replaces that scan. It is constructed for each lookup and never persists between calls. It keeps the original rules for nested dimensions, filters, exclusions and distinct types at the same path.

The isolated implementation and focused tests are [abffaa417](https://github.com/grouville/dagger/commit/abffaa417), on upstream main `4e1042289`. No PR is open.

| Entries, two per collection | Original lookup | Indexed lookup | Original allocations | Indexed allocations |
| --- | ---: | ---: | ---: | ---: |
| 20 | 217 µs | 44 µs | 109 KB | 37 KB |
| 200 | 18.0 ms | 0.45 ms | 8.29 MB | 0.37 MB |
| 2,000 | 1.78 s | 4.39 ms | 803 MB | 3.69 MB |

These are median microbenchmarks with data already in memory; indexed timings include constructing the index. They are not cold-engine or complete Rust build timings. Focused collection tests pass with the race detector on current upstream. A separate adversarial comparison matches the original algorithm across 2,048 generated path, dimension and filter combinations.

An actual API fixture has 512 sibling checks in one collection and requests its keys through the normal check type filter. Across eight alternating pairs, the index candidate is faster in every pair: medians are 11.98 and 8.56 s, with 1.80 s median paired saving. Observed CPU pressure reaches 71%; keep all samples and do not treat those medians as a stable latency estimate.

## Share module schemas within discovery

The next wcprof capture still records 1,053,810 events after indexing. Key expansion calls `Artifact.Evaluate` for each sibling. Each call rebuilds a fresh module server and installs all 512 functions. The resulting 263,169 `Query.typeDef` calls, 263,169 `TypeDef.withKind` calls and 525,312 `TypeDef.withOptional` calls mostly hit the cache, but still consume time and memory. CPU profiles attribute most active work to module installation through `expandArtifactNode`, rather than to compiler execution.

The second prototype shares fresh module servers within one expansion, using the module result ID, query, client ID and workspace result ID. It retains separate scopes and ordinary function calls; it does not cache collection keys. There is no reuse of the discovering session's server or a cache spanning expansions.

The separate implementation is [5a1a7af36](https://github.com/grouville/dagger/commit/5a1a7af36), on top of the index branch. Focused unit tests pass with the race detector. The new integration test checks two workspace values together, followed by an edit and restoration. It and the existing test that evaluates an artifact after its discovering session closes pass on the owned candidate engine. Additional actual CLI checks pass across fresh sessions and with mixed workspace values in one expansion.

On the same real API fixture, eight fresh-edit alternating pairs improve from **7.78 s to 0.491 s**, with **7.29 s median paired saving** and all eight pairs faster. Telemetry stays enabled, wcprof is disabled during timing, and every result contains the same two keys. Observed CPU/I/O pressure reaches 22.5%/13.9%. A separate capture drops to 6,298 events while retaining all 512 collection calls. These measurements concern key discovery, not Rust compilation.

The small CLI experiment that resolves `currentWorkspace` before validating dimension flags has no convincing speedup: matched edited-command medians are both 1.293 s, with five of eight pairs faster. It remains unselected. This distinguishes a repeated API operation from work whose removal actually reduces latency.

## Share schemas through deferred check execution

Discovering collection keys and running their checks are separate operations. Even after the discovery fix, each check rebuilt its module schema when preparing its value and again when running its deferred function. [fdae12f20](https://github.com/grouville/dagger/commit/fdae12f20) extends sharing through one `Artifacts.values` operation and the deferred check call. The check's own workspace is set before looking up its schema. Actual check outcomes remain independently evaluated.

A fixture with 64 sibling functions and two collection keys executes 128 checks. Each receives the workspace and reads `application.rs`; every measured command changes that file. Across eight alternating pairs, full-command medians improve from **3.55 s to 2.77 s**, with **740 ms median paired saving**, all eight pairs faster, telemetry enabled and wcprof disabled. Module loading and engines are warm; this measures checks after workspace edits, not a cold engine or Rust compilation. CPU/I/O pressure reaches 17.8%/3.5%. The timing harness's subprocess timeout polling adds up to roughly 50 ms of timing granularity, well below this measured gain.

Separate wcprof captures preserve all 128 Dang invocations and reduce events from 216,416 to 117,985. `Query.typeDef` calls fall from 66,821 to 33,926. Much work remains: each of 128 internal clients still installs the module's functions when its check reads the workspace. Sharing that installation while retaining each client's own query root is the next experiment.

Focused collection, batch, check-persistence and job-cancellation tests pass with the race detector. The integration regression now evaluates checks from two workspace values concurrently, verifies a failing edit, then restores the original source. It and evaluation after the discovering session closes pass on the candidate engine.

The small native Rust collection fixture batches its packages into one check and has **no established improvement** from this change: initial medians are both 1.217 s, with four of eight pairs faster. A second series removes subprocess timeout polling but encounters substantial CPU/I/O stalls, including 10–13 s control outliers; all samples are retained, and that series does not establish a Rust speedup either.

Recreate the edited-check fixture with `python3 hack/rust-cache/experiments/collection-discovery/fixture.py /tmp/collection-checks --checks 64 --workspace-input`. Change `application.rs` before each `dagger check` invocation. The command must execute 128 passing checks.

## Reuse module installation across internal clients

The remaining type-definition calls come from the client each check opens to read its workspace. Each internal client installs the module's 64 functions again. [ff1d703d7](https://github.com/grouville/dagger/commit/ff1d703d7) builds the module registry in the existing session memo and forks that registry onto each client's own query root. Changed module sets discard the template and build independently. The session owns the template; cached module values retain no session server.

With the previous check-execution fix already on both engines, eight alternating edited-command pairs improve from **3.34 s to 2.32 s**, with **1.01 s median paired saving** and all eight pairs faster. CPU/I/O pressure reaches 37.1%/2.5%. A separate profile reduces `Query.typeDef` calls from 35,922 to 1,160 and total events from 143,224 to 19,953, while preserving 128 Dang invocations.

A direct comparison of **both check-execution fixes together against their original control** gives **4.33 s to 2.30 s**, with **2.05 s median paired saving**, all eight pairs faster, telemetry enabled and wcprof disabled. This is the complete command running 128 checks after workspace edits; it includes discovery. Engines and module loading are warm. CPU/I/O pressure reaches 41.2%/7.9%. This direct series supersedes adding savings from separate measurement periods.

Concurrent-client regression tests verify one module installation with eight distinct query roots. Existing schema lifetime and cancellation tests pass with the race detector. Real-engine checks pass for mixed workspaces, an edited failure and restoration, closed discovering sessions, valid and invalid check return types, and four self-call cases returning module objects. The separate CLI projection test used an incompatible CLI, then stalled on its assumed in-engine Unix socket; it does not establish a candidate failure or a complete pass.

The small native Rust collection still has no established speedup: medians are **1.299 s versus 1.319 s**, only three of eight candidate runs faster, versus Cargo's **0.504 s**. One candidate outlier coincides with 60.6% I/O pressure. Keep all samples and do not select this change as a Rust performance improvement yet. Its established benefit is check execution with many functions. Further profiles across the Rust execution path are recorded in [NATIVE_PERF_PROFILE.md](NATIVE_PERF_PROFILE.md).

## Compare JSON decoders on the actual schema

The exported Rust module schema is 591,925 bytes. Three repeated decoder benchmarks give:

| Decoder | Warm decode | Allocated bytes |
| --- | ---: | ---: |
| Standard `encoding/json` | 10.13 ms | 3.14 MB |
| Standard API with Go's jsonv2 backend | 6.57 ms | 3.00 MB |
| Sonic 1.15.4, compatibility mode | 2.85 ms | 1.55 MB |

Both decoder comparisons preserve the decoded schema's complete value. Sonic's generated decoder is already prepared in those benchmarks. In six fresh processes, the first decode takes 114 ms median with Sonic versus 20 ms with the standard library, excluding process startup and file reading. This experiment changes no production dependency. A warm decoder improvement alone does not justify a replacement; startup cost, supported platforms and complete-command timing still need consideration. See the [Sonic implementation](https://github.com/bytedance/sonic) and [Go JSON experiment](https://go.dev/blog/jsonv2-exp).

Recreate the large collection fixture with `python3 hack/rust-cache/experiments/collection-discovery/fixture.py /tmp/collection-discovery --checks 512`. From that directory, run `dagger api query --doc keys.graphql`: it must return `a` and `b` without executing any check. Compare engines after warming module loading; source edits outside `many/` exercise fresh workspace imports without changing the check count.

Raw artifacts are under `/tmp/rust-cache-sipsma-review`: `collection-stack-paired`, `collection-stack-profile`, `collection-schema-sharing-paired`, `collection-schema-sharing-profile-rerun`, `check-schema-sharing-paired`, `check-schema-sharing-profile-control`, `check-schema-sharing-profile-final`, `nested-schema-forks-paired`, `nested-schema-forks-profile-*`, `check-schema-combined-paired`, `rust-check-schema-sharing-paired`, `rust-check-schema-sharing-refined`, `rust-nested-schema-forks-paired`, `schema-json-libraries`, and the focused `artifact-dimension-key-*` logs. The validated engine branches are pushed to the fork, with no upstream PR. They are not yet defaults for the Rust module prototype.
