# Fresh syntax from cached module parsing

The prototype removes most repeated parsing from the real Rust module. Its
latest phase captures fall from 69–87 ms to 3.5–3.8 ms for edited test, leaf and
shared-library commands. The complete-command comparison remains provisional:
check medians improve, the test median regresses, and the host is heavily
contended. No default behavior or dependency has changed.

## What is reused

The cache stores instructions for constructing the parsed syntax. It builds
these instructions before inference or evaluation, keyed by the filename and
SHA-256 of the file's current contents. Every use constructs fresh pointers and
slices. Inference and evaluation still run with the call's current schema,
client and imports. The original parsed tree is never handed back on a cache
hit.

The first parse returns its original tree after saving the construction
instructions. Unsupported fields skip caching and return the freshly parsed
tree. Parse errors retain the existing recovery path. Only the parser's static
operator evaluation functions are shared. No compiler input, native snapshot
identity or telemetry setting changes.

The implementation uses reflection once to build the construction instructions,
then executes those instructions on a hit. It is an experimental library patch,
not a shared evaluated-module environment. That distinction matters because
inference mutates syntax nodes and imports retain schema and client bindings.

## Measurements

Three microbenchmark samples against the actual Rust module give 2.17–2.19 ms
for a warm file read, digest and fresh syntax construction, with 622,168 bytes
and 15,205 allocations per call. The earlier parser baseline is about 68–72 ms
and 26 MB per call. A memory probe after garbage collection measures about
1.5 MB retained for one Rust module's construction instructions.

The engine comparison uses the same module commit `7d5c1a4`, engine base
`1770e627a`, parser grammar, opt-in statistics fix and diagnostic instrumentation
on separate local engines. Twelve rounds rotate baseline, candidate and Cargo.
Each command sees a unique source edit, with separate source trees and Cargo
targets. wcprof is disabled during timing; telemetry remains enabled.

| Edited command, median | Baseline | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 1.881 s | 1.984 s | 0.644 s | 8/12 pairs |
| Leaf edit, 102 actions | 1.560 s | 1.028 s | 0.146 s | 10/12 pairs |
| Shared edit, 102 actions | 2.612 s | 2.311 s | 1.508 s | 9/12 pairs |

CPU stalls reach 87.9% and I/O stalls reach 85.3% in these measured commands.
Cargo controls vary substantially. The candidate test outlier of 17.56 s is
retained. No cause is assigned to it beyond recording the concurrent host
pressure. These numbers do not establish a general command speedup or attainment
of the Cargo-plus-0.5-second target.

The six complete phase captures confirm the intended work reduction:

| Parse phase | Baseline | Candidate |
| --- | ---: | ---: |
| Test command | 72.16 ms | 3.82 ms |
| Leaf edit | 68.86 ms | 3.81 ms |
| Shared edit | 86.94 ms | 3.47 ms |

Those are individual phase durations. The inherited diagnostic hook nests
later phases under the completed parse operation; it must be corrected before
using those parent links to claim a critical-path reduction. No events are
dropped and no operations remain open.

## Correctness and remaining work

The focused isolation tests verify that mutations to a previous tree do not
affect a hit, changed source is reparsed, invalid source keeps its diagnostic,
and sixteen concurrent evaluations have independent state. The same source
uses a new client in a later call and rejects an incompatible new schema.
The language corpus also checks that supported syntax can be reconstructed
without changing its formatting. These tests pass with race detection.
Dang's language, formatting and error-message fixtures pass.

All 72 untimed native compiler cache probes pass after the measured commands:
5/5 test actions and 102/102 check actions reusable. Cargo checks the expected
2 crates for leaf edits and 102 for shared edits. Invalid Rust and changed
runtime data fail on both engines, then pass after restoration.

The prototype limits the cache to 128 files but has no byte budget. At the
measured 1.5 MB per Rust module, 128 similar entries could retain roughly
195 MB. A production version needs a memory budget or a more compact syntax
representation, an eviction regression, and a quieter full-command comparison.
Duplicate concurrent misses are correct but can repeat parsing and transient
allocation. Cache state is local acceleration; restart or eviction simply
parses again. The Rust compiler cache remains native Dagger snapshots.

Artifacts are under `/tmp/rust-cache-sipsma-review/module-parse-blueprint-paired`.
The [library experiment](experiments/dang-parse-blueprint/README.md) includes
the patch and focused tests. No upstream PR has been opened.
