# Remove nested packages in one snapshot

A package at the workspace root owns its files, but not the sources of its
nested packages. The Go compiler submodule removed each immediate child with a
separate `Directory.withoutDirectory` operation. A root package with 129 children
therefore needed a chain of 129 snapshots before its digest was available.

The variant passes those paths to one existing `Directory.withoutFiles` call.
Both APIs use the same path-removal implementation, in the same path order.
Packages with zero or one child keep their existing recipe. This changes the
graph preparation in the Go submodule; the Dang interface and the Go execution
program inside the Rust container are unchanged.

Implementation: [a8ede44 on Guillaume's fork](https://github.com/grouville/dagger-rust/commit/a8ede44).
The branch is isolated and no upstream PR has been opened. The surrounding native
Rust cache still requires the experimental engine; this change adds no engine API.

## Complete edited commands

The fixture has 128 leaf libraries, one shared library and an application at the
workspace root: 130 crates. The command is the real `dagger check rust:check`.
Every measured command follows a new, used source edit. A leaf edit rebuilds two
crates, a shared-library edit rebuilds all 130, and a root edit rebuilds one.
Native Cargo logs verify those rebuild sets.

Both module versions use the same warm engine and independent native histories.
The control is `b4b8ffd`; the engine includes the primitive-array response
experiment. Rust 1.77.2 runs with eight-way compiler concurrency. Invocation order
rotates between control, candidate and native Cargo. Telemetry remains enabled
to the local receiver and wcprof is disabled. The timer uses blocking `waitpid`,
without Python's timeout polling. Two preparation rounds are excluded.

Eight pairs per scenario:

| Edit | Control median | Batched median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Leaf | 1.450 s | 0.798 s | 0.097 s | 667 ms | 8/8 |
| Shared library | 2.227 s | 1.448 s | 0.659 s | 808 ms | 8/8 |
| Root package | 1.444 s | 0.758 s | 0.079 s | 728 ms | 8/8 |

The implementations are then swapped between the existing histories, prepared
again and measured with eight further pairs:

| Edit | Control median | Batched median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Leaf | 1.453 s | 0.718 s | 0.097 s | 721 ms | 8/8 |
| Shared library | 2.114 s | 1.420 s | 0.614 s | 694 ms | 7/8 |
| Root package | 1.414 s | 0.717 s | 0.077 s | 693 ms | 8/8 |

The benefit survives the swap. The results apply to workspaces containing a
package with many nested packages. A virtual workspace has no such root package
to project. The Cargo +0.5 s target remains unmet, including the leaf case.
These savings are relative to this control and must not be added to medians
from earlier experiments.

All samples and pressure measurements are retained, including a 5.556 s control
shared edit, a 4.163 s Cargo shared edit, and the crossover candidate's 3.608 s
shared edit. Host and engine stalls are recorded separately. No unrelated test,
build or capture runs alongside the timings.

## Verify the work and cache identity

Fresh leaf-edit wcprof captures have no dropped events or open operations:

| Work | Control | Batched |
| --- | ---: | ---: |
| Executed `Directory.withoutDirectory` calls | 129 | 0 |
| Executed `Directory.withoutFiles` calls | 0 | 1 |
| Executed package/other `Directory.digest` calls | 133 | 133 |
| Recorded events | 8,381 | 6,718 |
| Go compiler submodule workload | 1,096.8 ms | 390.5 ms |
| Compilation program workload | 63.4 ms | 69.7 ms |

The compilation program runs inside the submodule's interval. The intervals
overlap and must not be added. These captures locate the removed work; their
wall times are not further command savings.

An explicit bridge probe reuses 130/130 results produced by the old recipe.
Post-crossover probes also recover all 130 results from each history, with
exactly one execution marker from the last root edit. Reuse is checked by
inspecting the native cache, rather than inferred from command time.

The engine-backed integration test compares each package's native directory
and digest with the previous sequential recipe. It covers nested packages,
siblings beneath a shared parent, special characters, lookalike names, a
symlink into an excluded package, and file and directory permissions. A nested
edit changes only its owning package's digest. Changing a root-owned file mode
changes only the root package's digest. The fixture explicitly replaces the
file to change its mode: overwriting with `withNewFile` preserves its old mode.

Replay, worker and model tests pass under race detection. The integration test
also passes under race detection against the actual engine.

## A larger root package now works

The same layout with 1,024 leaves has 1,026 crates. The old recipe fails during
snapshot mounting with `mount options is too long`. Batching the exclusions
lets the ordinary check complete. The first candidate command takes 35.3 s,
including cold capture and preparation; this is a correctness/scalability
result, not a warm latency comparison with the failing control.

A subsequent leaf edit compiles exactly two actions. Its next native probe
recovers all 1,026 results without host cache metadata.

The [fixture generator](experiments/native-worker-index/fixture.py) accepts
`--root-package`. The [measurements and profile summaries](experiments/native-package-exclusions/measurements.json)
preserve both series, and the experiment directory contains the command drivers.
