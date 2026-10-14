# Bounded module parsing cache

The [fresh-syntax prototype](NATIVE_PARSE_CACHE.md) now evicts by a 64 MiB
construction-weight budget as well as its 128-file limit. Weighted eviction,
oversized fallback and concurrent misses pass regression tests with race
detection. This remains a library experiment, with no dependency update or PR.

## Memory and correctness

Construction weight accounts for instructions, reflected scalar/type storage,
child slots and string bytes. Strings are detached from parser buffers before
retention. This is an estimate of retained memory, not an exact Go heap limit.
Oversized or unsupported syntax returns the original freshly parsed tree and
skips caching. Parsing and fresh construction run outside the cache lock.

After fifty versions of the actual Rust module, a garbage-collection probe
measures 22,952,072 bytes of retained heap, fourteen entries and 63,917,252
accounted bytes under the 67,108,864-byte budget. The probe is kept outside the
proposed test patch. It is one local measurement, not a general heap bound.

The regressions cover least-recently-used eviction, both weight and entry limits,
duplicate concurrent publication, reconstruction after eviction, and use of an
entry already obtained while another caller evicts it. The earlier syntax,
source-change, schema, client and concurrent-evaluation checks remain enabled.
The language and type-inference unit suites pass with race detection, including
reconstruction of the language corpus and the actual Rust module.

## Matched engine comparison

The engine baseline and candidate use the same module, engine base, parser and
diagnostic instrumentation. The phase hook is corrected in both: parsing,
inference and evaluation now have the same parent. The twelve-round comparison
uses unique edits through normal Rust commands, independent source trees and
Cargo targets, and rotating command order. wcprof is disabled during timing;
telemetry stays enabled.

| Edited command, median | Baseline | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 1.453 s | 1.406 s | 0.446 s | 7/12 pairs |
| Leaf edit, 102 actions | 1.137 s | 1.097 s | 0.106 s | 7/12 pairs |
| Shared edit, 102 actions | 1.888 s | 1.641 s | 0.688 s | 11/12 pairs |

All 72 compiler-cache probes pass. The six profile captures have no dropped
events or unfinished operations, and the three preparation phases share their
parent as intended. Parsing reads 128.16→2.00 ms for tests, 65.56→2.03 ms for
leaf edits and 65.94→2.14 ms for shared edits. These are phase durations, not
additional command gains.

CPU stalls reach 84.1% and I/O stalls reach 72.7% during measured commands. The
series therefore remains provisional, including its favorable shared-edit
median. Artifacts are under
`/tmp/rust-cache-sipsma-review/module-blueprint-bounded-paired`.

## Benchmark environment cleanup

Thirty older owned Rust experiment engines were still running. Each lifecycle
endpoint reported zero sessions and zero active requests before shutdown. Their
cache volumes were preserved. The two engines used for comparison were kept,
along with one older engine without a published debug endpoint whose idleness
could not be verified. Unrelated containers were untouched.

The follow-up uses the same binaries and already prepared independent source
trees and Cargo targets after that cleanup. Shutdown work is outside the timed
commands. Removing idle experiments improves the measurement setup; it does not
prove a performance improvement in Dagger. The audit and stop results are under
`/tmp/rust-cache-sipsma-review/idle-engine-audit`.

The twelve-round confirmation retains every sample, including the 3.45 s Cargo
test outlier. It gives:

| Edited command, median | Baseline | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 1.056 s | 0.952 s | 0.356 s | 11/12 pairs |
| Leaf edit, 102 actions | 0.857 s | 0.797 s | 0.088 s | 10/12 pairs |
| Shared edit, 102 actions | 1.399 s | 1.351 s | 0.532 s | 10/12 pairs |

Median savings within each pair are 97.7 ms for tests, 60.1 ms for leaf edits and
30.3 ms for shared edits. These differ from subtracting the two column medians.
CPU stalls peak at 28.6% and I/O stalls at 56.1%, so the magnitude is still
specific to this local study. The consistency across pairs and the phase
captures support a local edited-command gain; they do not prove a universal
gain or eliminate the remaining Cargo gap.

The complete confirmation profiles record parsing at 65.26→2.16 ms for tests,
106.88→2.03 ms for leaf edits and 63.36→2.04 ms for shared edits. All 72 cache
probes pass, Cargo checks the expected crates, and all six captures are complete
with sibling phase parents. Artifacts are under
`/tmp/rust-cache-sipsma-review/module-blueprint-bounded-confirmation`.

The candidate also rejects invalid Rust and changed runtime data, then restores
all 5/5 compiler hits and passes the normal test command after reverting each
failure. A clean engine restart recovers 5/5 native compiler results, rebuilds
the parsing cache, and passes normal tests. A subsequent application edit reuses
2/5 compiler actions and passes normal tests. These checks are under
`/tmp/rust-cache-sipsma-review/blueprint-bounded-rust-correctness`.

The [bounded library patch and regressions](experiments/dang-parse-blueprint-bounded/README.md)
are available for review. Remote compiler state remains native Dagger snapshots;
the parsing cache is local acceleration and can be rebuilt after eviction or
restart. Real registry dependencies, build scripts and procedural macros remain
outside the current compiler prototype's supported boundary.
