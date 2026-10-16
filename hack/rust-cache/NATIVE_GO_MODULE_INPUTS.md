# Read Go module call inputs in one request

This change is in the Go SDK code generator in `dagger/dagger`. The earlier
[Go test-discovery change](upstream-prs/go-package-test-discovery.md) is in the
Dang module `dagger.io/go`. They are separate changes. This study uses the Go
compiler helper inside the experimental Rust module as its workload.

A generated Go entrypoint fetches the parent name, function name, parent JSON and
argument list, then each argument's name and value. With A supplied arguments,
that is 4 + 2A metadata requests. Select the same fields together and preserve
JSON as serialized strings. The existing method invocation and return paths
stay in place. There is no new engine API or retained cache.

The [standalone source and regression](https://github.com/grouville/dagger/commit/af040470362736cf72f56d7a9f5365564fa2a751)
are based on current main `ff0b029a4d`. The measured Rust helper supplies 12
arguments, so it goes from 28 metadata requests to one. Its generated dispatch
block matches the changed template byte for byte. The
[Rust experiment](https://github.com/grouville/dagger-rust/tree/experiment/test-collection-batched-inputs)
is pushed separately; regenerating it with an older code generator replaces
that experimental block. Neither branch opens a PR or changes the selected
workspace batch module.

## Complete edited commands

| Command | Before | Batched reads | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Collection, one package | 0.813 s | 0.689 s | 141 ms | 3/4 |
| Collection, 16 packages | 2.316 s | 2.225 s | 91 ms | 3/4 |
| Collection, 64 packages | 8.602 s | 8.253 s | 190 ms | 3/4 |
| Collection, 64 packages, confirmation | 8.922 s | 8.095 s | 884 ms | 7/8 |
| Workspace API, 64 packages | 0.917 s | 0.927 s | 4 ms | 3/6 |

The two large-collection cohorts establish 10/12 faster pairs, with substantially
different gain sizes. The workspace control establishes no speedup: its median
allocation is 220 → 227 MB and engine CPU 0.91 → 0.96 CPU-second. In the collection
confirmation, allocations fall 6.96 → 6.73 GB and engine CPU 46.85 → 42.77
CPU-seconds. Allocation totals are cumulative, not peak live memory.

Every arm edits the same physical source to a fresh positive value and starts a
fresh CLI. The engine, compiler and toolchain caches are warm. Telemetry and
natural GC stay enabled. Before/after placement is balanced. Native Cargo and
the workspace batch remain controls; Cargo takes about 0.31 seconds in the
confirmation. Each package has eight real unit tests; fixture doctests are
disabled. All attempts, pressure, GC counts and warmups are kept. The timings
use diagnostic engine `2a32d997c29c…`, not an engine rebuilt from today's main.

This cohort starts from the combined compilation/discovery branch. Its saving
must not be added to the preceding experiment's medians. Fine collections remain
much slower than the workspace batch, and remain unselected.

## Trace and correctness

The final isolated wcprof captures record **5,097 → 3,369 engine queries**,
**768 → 0 argument-ID reads**, and the same **193 workloads**. Both dumps have
zero lost events and no unfinished operations. One earlier CPU window overlapped
an initial unit test; it is retained with a note and is not used for attribution.
The final captures run after all tests and timing cohorts finish.

The runtime regression compiles the actual template output and uses the real SDK
HTTP transport. It checks empty arguments, exact JSON values, method errors and
metadata errors. The mock serves the old request shapes too: main preserves the
data but fails the single-request requirement; the patched template passes.
Focused generator tests and the template race suite pass. Rust integration checks
cover arbitrary subsets, selected/excluded test failures, excluding an invalid
crate, repair and the workspace API. Worker build inputs and native-cache format
are unchanged.

The five-second final CPU window still contains substantial allocation and GC
work. Wcprof records 768 argument-name and 768 argument-value reads even after
batching; server work still scales with the number of arguments. It also records
17,154 cached `Query.typeDef` calls. Those concurrent class durations cannot be
added to explain wall time. The next useful investigation is the engine cost of
these field reads and repeated schema preparation, using CPU evidence and the
recorded blocking paths before changing their behavior.

[Review description](upstream-prs/go-module-batched-inputs.md) and
[complete evidence](experiments/go-module-batched-inputs/) are ready. The source
change replaces 26 lines with 16; the transport regression is its only new test.
This is the eleventh prepared Dagger proposal, separate from the Go-module
proposal. No upstream PR is open.
