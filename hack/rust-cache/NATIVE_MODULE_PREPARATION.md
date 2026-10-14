# Native Rust module preparation

The latest profiles put most Dang module preparation time in parsing. Nine
captures cover fresh source edits through the normal `rust:test` command and
leaf and shared-library edits in the 102-action `rust:check` workspace. Compiler
results and incremental state remain native Dagger snapshots; telemetry stays
enabled.

| Phase | Median | Range |
| --- | ---: | ---: |
| Parse module source | 68.46 ms | 64.59–84.05 ms |
| Decode API schema | 9.61 ms | 8.42–16.26 ms |
| Type inference | about 2.6 ms | 2.49–3.03 ms |
| Evaluate module declarations | about 0.6 ms | 0.58–0.66 ms |

These are diagnostic phase measurements, not a before/after command comparison.
The profiles contain no dropped events or unfinished operations. Artifacts are
under `/tmp/rust-cache-sipsma-review/module-preparation-phase-profile`.

## Process creation is now a smaller part

The same nine captures contain 33 fresh executions. Their median command-spawn
phase is 0.79 ms, init preparation is 1.93 ms, root filesystem setup is 0.89 ms,
and runtime creation reads 3.33 ms. Runtime creation uses a coarse pid-file
timestamp, so this last reading is an estimate. These phases exclude earlier
snapshot construction, query handling and output publication.

The earlier matched [crun comparison](FRESH_PROCESS_START.md) measured two runtime
starts falling from 75–103 ms to about 21–22 ms. It is a stronger before/after
comparison than readings from unrelated captures. The compiler worker already
batches misses; it does not start a container for every crate.

The Go helper currently owns plan validation, source hashing, exact-result and
incremental-seed selection, graph construction and publication. Eliminating its
launch requires moving that implementation into another runtime. A direct Dang
port would duplicate substantial logic and needs a complete-command measurement
to justify that cost. No helper has been removed in this study.

## Parser experiments

The parser grammar is generated with the existing opt-in choice-statistics fix.
Enabling counters accidentally in one variant would invalidate a comparison.
The initial microbenchmarks parse the actual Rust module source.

- Memoization increases the median from 72.3 to 128.1 ms and allocated bytes from
  26.3 to 122.7 MB per parse. It is rejected.
- Basic Latin lookup gives 72.7 ms and no meaningful allocation improvement.
  It is rejected.
- The optimized-parser option gives 63.9 ms, but removes debug, memoization and
  statistics options from the parser API. It has not been selected.
- Grammar optimization generates duplicate parameter names and does not build.
- Grouping runs inside multiline string parsing gives 95.8 ms and only a small
  allocation reduction. It is rejected.

The smallest viable experiment returns unused saved-state maps to the existing
pool when a choice, sequence or left-recursive growth succeeds. Failure paths
still restore the saved state. The regenerated parser changes three lines and
leaves its grammar and option API unchanged. Its initial microbenchmark gives
67.5 ms, 24.0 MB and 361,531 allocations, compared with 72.3 ms, 26.3 MB and
409,553 allocations. Sequential microbenchmarks alone cannot prove command
latency improves.

The generator's existing state restoration, cloning, read-only state, empty
state, goto state and left-recursion tests pass with race detection after
regenerating their parsers. Dang's language and type-inference unit suites also
pass with race detection. Language execution, formatting and diagnostic fixtures
pass. A differential check over 472 files, including the Rust module, produces
identical syntax trees and errors with memoization both enabled and disabled.

No allocation-count unit test is retained: the pool may discard maps during
garbage collection and race instrumentation. Allocation changes belong in the
benchmark; the existing tests check state semantics.

The generator patch, generated parser patch, build logs and correctness results
are under `/tmp/rust-cache-sipsma-review`. The engine instrumentation and
`RunDirProfiled` callback are local diagnostics, not a production API proposal.

## Complete-command comparison

The comparison uses the same module commit and engine code on two isolated
engines, changing only the generated parser. Both include the same phase
instrumentation. It prepares independent source trees and Cargo target
directories for test, leaf-edit and shared-edit scenarios, then rotates the
order of baseline, candidate and Cargo over twelve rounds. Every edit is unique.
Profiles are disabled during timing; telemetry remains enabled. Untimed probes
check complete compiler-result reuse after each measured command.

The first engine setup is excluded. Those preparation calls must not be read as
proof of a cold compilation: identical source can already match an execution
result in the engine. Fresh edits and compiler-cache probes provide the relevant
edited-build evidence.

| Edited command, median | Baseline | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 1.756 s | 1.712 s | 0.680 s | 5/12 pairs |
| Leaf edit, 102 actions | 1.369 s | 1.234 s | 0.143 s | 7/12 pairs |
| Shared edit, 102 actions | 2.286 s | 2.448 s | 1.397 s | 5/12 pairs |

Host stalls reach 83.0% for CPU and 81.1% for I/O during these measured commands.
The Cargo controls also vary substantially. All 72 untimed native cache probes
pass: 5/5 test actions or 102/102 check actions reusable after each command.
Cargo's leaf and shared edits check the expected 2 and 102 crates respectively.
All six phase captures are complete, but their parser times are inconsistent:
test 70.8→109.6 ms, leaf 76.8→94.5 ms, shared 76.9→66.8 ms. These readings do
not establish a command latency improvement. The candidate is not selected.
Changing only a runtime data file makes tests fail on both engines; restoring
it makes them pass again.

Artifacts are under `/tmp/rust-cache-sipsma-review/module-state-pool-paired`.
The [generator patch](pigeon-state-pool.patch) and
[regenerated parser patch](dang-state-pool.patch) preserve the small experiment
for a quieter confirmation or upstream allocator review. They apply on top of
the earlier opt-in choice-statistics change. No PR has been opened.
The saved patches omit context; use `git apply --unidiff-zero`.

The [engine instrumentation](module-preparation-profile.patch) applies to engine
commit `1770e627a`. It also needs the
[Dang phase hook](dang-module-phase-profile.patch) in the local library. A
baseline and candidate engine must use identical instrumentation. These are
diagnostic patches, not changes to install in the official Rust module.
The phase hook preserves the parse context after parsing, so its later phases
appear under that completed parse operation. The table uses each phase's
recorded duration; these captures must not be used to claim a parent/child
critical-path reduction without correcting that diagnostic hook first.

The next larger module opportunity is avoiding repeated parsing while giving
each call fresh syntax state and a client bound to the current session. Reusing
an evaluated module environment directly is unsafe: inference mutates syntax
nodes, and imports retain schema and client bindings. A parser cache needs an
immutable representation and a verified fresh-copy path. Helper elimination
and prepared-container execution remain unmeasured alternatives.
