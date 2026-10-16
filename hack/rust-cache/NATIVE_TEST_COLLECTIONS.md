# Rust and Go test collections

The collection ancestor index is present in the measured engine. Its earlier
benchmark covered 1,000 collection fields, rather than 1,000 package items under
one field. This comparison exposes additional costs in package and test discovery
and execution.

## A scoped Go module improvement

The official Go module at `334136faaa` repeats a module-wide test-name search while
expanding each package. A 16-package profile records 2,176 search-result item
reads: 128 tests inspected during package discovery and again for each package.
The `SearchResult.search` rows include array-item access; they are not 2,176
separate searches. There are 18 executed `Workspace.search` operations.

[The change on Guillaume's fork](https://github.com/grouville/go/commit/9a1ea73ec6dffa72e3f450ea413ad93bc323ecd8)
searches each package's immutable test files with the existing engine matcher.
It preserves filename order and supports workspace overlays. The added Unicode
cases pass on main and the final patch; they reject the earlier attempt to match
file contents with Dang's different regular-expression implementation.

| Edited Go collection | Main | File searches | Allocated bytes, main → branch |
| --- | ---: | ---: | ---: |
| 16 packages, 128 tests | 4.52 s | 2.36 s | 3.50 → 1.19 GB |
| 64 packages, 512 tests | 55.11 s | 8.12 s | 40.92 → 4.47 GB |

Four balanced pairs at each size; all eight improve. The 64-package baseline
ranges from 47.4 to 62.8 seconds and the candidate from 7.85 to 8.70 seconds.
All observations are retained. These are allocated bytes over each command,
not peak live memory. The final 64-package diagnostic executes two workspace
searches and accesses 1,024 result items, including the per-file results. It
starts 65 workloads: the shared scanner and 64 package test executions.

Smaller controls establish no general latency improvement. One package with one
test file stays at 0.93 seconds median, with a 29 ms median paired slowdown. A
single package with 16 test files measures 1.30 → 1.38 seconds, with an 85 ms
paired slowdown and 2/4 faster pairs. It allocates about 42 MB less. Searching
per file has a startup cost, which remains an explicit tradeoff in the proposal.

The [review description](upstream-prs/go-package-test-discovery.md) is prepared.
The branch is pushed; no upstream PR is open. The ten prepared Dagger engine/CLI
proposals remain a separate batch.

## Match Go's selection levels in Rust

[The isolated Rust branch](https://github.com/grouville/dagger-rust/tree/experiment/test-collection-granularity)
exposes package and individual-test dimensions. Standard libtest harnesses supply
the actual test names; doctests remain one entry per target. This experiment
requires `nativeCache = true`, and listing tests can compile their harnesses.
The ordinary workspace test function remains callable through
`dagger api call rust test --source .` and no longer adds a duplicate test check.

| Packages, eight tests each | Rust workspace | Rust collection | Cargo |
| --- | ---: | ---: | ---: |
| 1 | 0.70 s | 0.76 s | 0.21 s |
| 16 | 0.78 s | 2.44 s | 0.23 s |
| 64 | 0.94 s | 9.80 s | 0.30 s |

These are four pairs per size on the final, correctly scoped implementation.
The first prototype shared compilation over the entire workspace and measured
5.46 seconds at 64 packages. A negative test then showed that selecting one
package still compiled an excluded invalid crate. Its faster number does not
establish the performance of correct package selection. The final version retains
compiler/test plans per package and passes that exclusion check.

Replay and worker race tests pass. Integration checks cover arbitrary test
subsets, a failing selected test, excluding that failure, full-package failure,
repair, excluding an invalid crate, and reporting the same crate error when all
packages are selected. Prepared execution containers remain typed Dagger values;
compiler outputs and incremental state remain native snapshots. The worker build
inputs and compiler-cache format are unchanged.

The final 64-package Rust profile starts 257 workloads, including compiler-module
calls, test discovery and package test execution. Constructing complete-package
executions during discovery avoids a further helper call for those executions,
but package-scoped compilation and discovery still cost too much. The selected
Rust module stays on its faster workspace batch. The finer branch is pushed for
experimentation, not selected as a performance improvement.

## Combine Rust compiler preparation and discovery

[The next isolated branch](https://github.com/grouville/dagger-rust/commit/76f4a5784be2ad0da6ccde4b69dca81ae0377073)
asks the existing compiler call to prepare the test collection. Discovery reuses
the loaded plan, native directories and worker reference, instead of starting a
second Go module process per package. Ordinary workspace compilation does not
request discovery. Package filtering, worker build inputs and the native compiler
cache format stay unchanged.

| Packages, eight tests each | Separate preparation | Combined preparation | Workspace batch | Cargo |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.90 s | 0.77 s | 0.88 s | 0.22 s |
| 16 | 2.73 s | 2.49 s | 0.88 s | 0.24 s |
| 64 | 10.20 s | 8.15 s | 0.87 s | 0.31 s |

These are a new cohort of four balanced pairs per size, with the same fresh-edit
protocol. All four one-package pairs improve, and three of four improve at each
larger size. The 64-package median paired saving is 2.13 seconds; one pair is
47 ms slower. Allocations fall from 8.06 to 6.90 GB and engine CPU from 52.35 to
42.84 CPU-seconds. Allocations are cumulative, not peak memory. Source hashes,
pressure, normal GC counts, every sample and warmups are retained.

Separate wcprof captures confirm 257 → 193 workload starts: 64 compiler calls,
64 test-listing runs, 64 package-test runs and one compiler miss. Both captures
have zero dropped events and no unfinished operations. The combined capture
still records 5,097 engine queries. The
[subsequent Go dispatch experiment](NATIVE_GO_MODULE_INPUTS.md) reduces these to
3,369 by reading arguments in one request; it measures that change in separate
cohorts and keeps the workspace control. The preparation experiment's five-second
CPU window also shows substantial allocation and GC work; that window does not
cover the entire command.

Replay and worker race checks pass. Integration checks cover arbitrary subsets,
excluded and selected failures, excluding an invalid crate, reporting it when
selected, repair and the workspace API with an explicit source. This branch is
pushed separately; the selected module remains on the faster workspace batch.
The ancestor index is enabled on both sides of this comparison.

[The preparation experiment archive](experiments/rust-collection-preparation/)
contains the complete measurements, source snapshots and profiles. Further work
must share preparation across selected items while keeping excluded packages out
of compilation, and reduce the API work within each module invocation.

## Measurement limits and real-repository diagnostic

Every timed arm makes a fresh Rust or Go edit and starts a new CLI process. The
engine, toolchains and compiler caches are warm. Telemetry and ordinary GC stay
enabled; wcprof and CPU profiling run separately. Native Cargo uses Rust 1.77.2,
incremental compilation and eight workers; native Go and the module use Go
1.26.6. These small independent packages establish selection overhead, not the
scaling of shared dependencies or real application test suites.

The diagnostic engine is `2a32d997c29c…`, with the existing ancestor index and
selected scalar/getter changes. Its directory-copy and span-index candidates
remain disabled. Source overlays and the exact binary identity are archived.

On real `dagger/dagger` sources, the original module's expanded listing did not
finish within 120 seconds. A full test-collection attempt with the Go patch also
reached the 120-second diagnostic limit. Both commands were cancelled; neither
reproduced an engine crash or OOM. The engine remained running and all clients
closed. The full repository still needs investigation, and these results do not
claim to fix its reported crash or establish a complete-suite speedup.

[Raw evidence](experiments/rust-go-test-collections/) preserves all cohorts,
profiles, source snapshots, failed harness assumptions and regression checks.
An auto-progress run returned success without rendering a final check table;
visible row counts were removed as an execution oracle. The final independent
profile verifies all 64 Go test workloads.
