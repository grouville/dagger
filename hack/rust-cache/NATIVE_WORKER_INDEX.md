# Build the compiler dependency index once

The execution program built a lookup table for every compiler it launched.
Each table contained every captured action, including unchanged dependencies.
For M changed actions and N captured actions, constructing those tables took
O(M × N) work before walking the required dependency closures.

The variant builds one table before starting the compilation goroutines. They
share read-only access until the batch finishes. Dependency traversal, private
filesystem views, compiler arguments, scheduling and output publication stay
the same. There is no new lock or dependency. The table is rebuilt for every
batch, including the first one; it is not retained between commands.

Implementation: [b4b8ffd on Guillaume's fork](https://github.com/grouville/dagger-rust/commit/b4b8ffd).
No upstream pull request has been opened.

## Isolate dependency preparation

The focused benchmark prepares every action in a wide graph whose leaves share
one dependency. Outputs are empty to isolate graph selection from filesystem
operations and `rustc`. Each measured iteration includes construction of the
new index. Medians across three runs:

| Actions | Before | One index | Bytes allocated before | One index |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 2.416 ms | 0.025 ms | 5.63 MB | 0.037 MB |
| 1,024 | 162.416 ms | 0.233 ms | 363.03 MB | 0.300 MB |

At 1,024 actions, allocation count falls from 1,069,065 to 1,029 per batch.
This establishes an algorithmic improvement in this component, not the time
saved by a complete Rust command. The graph, code and benchmark data are warm;
the index is newly constructed on every iteration.

The [raw samples](experiments/native-worker-index/microbench.json) preserve
all three measurements at each size. Replay, worker and model unit checks
pass with race detection.

The [workspace generator](experiments/native-worker-index/fixture.py) produces
1,024 leaf libraries, their shared dependency and an application: 1,026 crates.
It supplies real Rust sources, pinned module configuration and a separate cache
key per variant. Generate `Cargo.lock` with the matching Cargo toolchain before
using the locked module.

## Complete edited commands

The actual Rust module uses the same compiler concurrency (eight) before and
after the change. Both variants run on the same warm engine, with independent
native histories. Every measured command follows a new edit; telemetry remains
enabled and wcprof is off. Invocation order rotates between the two variants
and native Cargo. Preparation runs are excluded.

| Scenario | Control | One index | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,026 crates, leaf edit | 3.750 s | 3.888 s | 0.795 s | −465 ms | 3/8 |
| 1,026 crates, shared edit | 11.119 s | 9.335 s | 5.901 s | 1,973 ms | 8/8 |
| Shared edit, histories swapped | 9.907 s | 9.374 s | 5.939 s | 431 ms | 6/8 |
| Small package test collection | 0.953 s | 1.008 s | 0.471 s | −51 ms | 3/8 |
| Small collection, histories swapped | 0.973 s | 0.970 s | 0.473 s | 10 ms | 8/12 |

The large command is `dagger check rust:check`; the small one is the actual
`dagger check rust:packages/test` collection, including tests and doctests.
Cargo runs the corresponding workspace check or test with the same toolchain,
offline dependencies and incremental compilation.

The shared-edit result survives swapping the implementations between the
existing cache histories, with a smaller gain. The first small series' slowdown
does not reproduce after that swap. Leaf edits execute only two compilations
and show no benefit. These results support removing the repeated table builds;
they do not establish a general command speedup or the Cargo +0.5 s target.

Changing the execution program changes its cache compatibility identity.
Four preparation edits follow each implementation swap before crossover
timing. All measured commands succeed. All samples and pressure measurements
are retained in [measurements.json](experiments/native-worker-index/measurements.json),
including the large crossover's final 20.888 s control, 23.618 s candidate and
14.174 s Cargo commands. Host I/O stalls reach 54% in the first large series
and 46% in its crossover; the owned engine's I/O stalls reach 22.7% in the
crossover. The magnitude remains sensitive to contention.

## Verify native reuse and failures

A fresh probe after an ordinary large leaf edit recovers all 1,026 cached
results. Its current batch contains exactly two execution markers, verifying
that the edit compiled the leaf and its dependent application. These probes
inspect native snapshots; elapsed time is not used to infer cache hits.

The small workspace checks exercise cached dependency artifacts, exact reuse
after restoring source, a syntax error, a changed file read by a test at runtime,
and a failing doctest. Each failure is reported by the normal Rust command;
restoring the inputs recovers the previous compiled results. Race checks pass
for the replay, execution and model packages. The shared map is built before
starting compilation goroutines, and those goroutines never modify it.

## The next large-graph costs

Two fresh shared-edit wcprof captures have no dropped or open operations.
Each still makes 71 requests from the Go submodule and 4,106 individual
`String.glob` item calls while returning source paths. The Go program inside
the compiler container takes 4.875 s and 4.817 s; its encompassing submodule
takes 8.705 s and 9.964 s. Those intervals overlap and must not be added.
The large difference outside the compilation program belongs to preparation,
engine requests and response handling, rather than the dependency index alone.

In the control's five-second engine CPU window, span export accounts for
3.54 CPU-seconds and span fetching for 2.39 CPU-seconds, with JSON conversion
prominent. These call trees overlap. The capture lies inside the edited
command and excludes the compiler container's Go and Rust CPU. It motivates
removing unnecessary graph operations and repeated telemetry conversions while
preserving telemetry; it is not a full-command CPU or latency attribution.
