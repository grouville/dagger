# Collection discovery and module loading

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

## Compare JSON decoders on the actual schema

The exported Rust module schema is 591,925 bytes. Three repeated decoder benchmarks give:

| Decoder | Warm decode | Allocated bytes |
| --- | ---: | ---: |
| Standard `encoding/json` | 10.13 ms | 3.14 MB |
| Standard API with Go's jsonv2 backend | 6.57 ms | 3.00 MB |
| Sonic 1.15.4, compatibility mode | 2.85 ms | 1.55 MB |

Both decoder comparisons preserve the decoded schema's complete value. Sonic's generated decoder is already prepared in those benchmarks. In six fresh processes, the first decode takes 114 ms median with Sonic versus 20 ms with the standard library, excluding process startup and file reading. This experiment changes no production dependency. A warm decoder improvement alone does not justify a replacement; startup cost, supported platforms and complete-command timing still need consideration. See the [Sonic implementation](https://github.com/bytedance/sonic) and [Go JSON experiment](https://go.dev/blog/jsonv2-exp).

Recreate the large collection fixture with `python3 hack/rust-cache/experiments/collection-discovery/fixture.py /tmp/collection-discovery --checks 512`. From that directory, run `dagger api query --doc keys.graphql`: it must return `a` and `b` without executing any check. Compare engines after warming module loading; source edits outside `many/` exercise fresh workspace imports without changing the check count.

Raw artifacts are under `/tmp/rust-cache-sipsma-review`: `collection-stack-paired`, `collection-stack-profile`, `collection-schema-sharing-paired`, `collection-schema-sharing-profile-rerun`, `schema-json-libraries`, and the focused `artifact-dimension-key-*` logs. Both engine branches are pushed to the fork, with no upstream PR. Neither is yet a default for the Rust module prototype.
