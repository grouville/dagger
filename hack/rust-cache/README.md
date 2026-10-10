# Rust compiler cache experiment

`rcexp` records Cargo's actual compiler commands and replays each compilation as
a Dagger operation. Package source and dependency artifacts are explicit inputs;
compiled artifacts are immutable outputs. No compiler cache volumes are used.

The new experimental path imports native source directories, automatically
retains rustc incremental state, and can run compiler misses together with Cargo's
metadata overlap. Completed results remain reusable per crate. These options are
described below; none changes the Rust module's default behavior.

This follows the Go package replay described in
[dagger/dagger#14555](https://github.com/dagger/dagger/pull/14555) and
[#14557](https://github.com/dagger/dagger/pull/14557).
Erik's `gcexp` implementation was unavailable when this experiment was written.

The existing [dagger-rust module](https://github.com/grouville/dagger-rust) is
the Cargo-facing layer: checks, toolchain selection and final artifact publishing.
This experiment explores a possible native compiler-cache backend for that
module. It currently supports a smaller set of projects, so integrating it should
start as an explicit experimental option while the module keeps its normal Cargo
execution for other projects. The cache-transfer integration test lives here
because it uses Dagger's internal test fixture.

Users should install one Rust module for their workspace. Compiler operations and
dependency edges are internal to its backend; no module per crate is needed.

## Run

Run from the repository root. Build the matching CLI so the Go SDK uses this
checkout's API and engine:

```sh
go build -o /tmp/dagger-rcexp ./cmd/dagger
export _EXPERIMENTAL_DAGGER_CLI_BIN=/tmp/dagger-rcexp

go run ./hack/rust-cache capture \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json

go run ./hack/rust-cache replay \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-cold \
  --report /tmp/rust-cold.json

go run ./hack/rust-cache replay \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-warm \
  --report /tmp/rust-warm.json --previous /tmp/rust-cold.json
```

Artifacts preserve their paths relative to `/target`; the fixture executable is
under `debug/deps/app-*` (without a file extension). Replay reports include
per-action artifact digests and execution markers. A matching marker means that
the cached filesystem was reused; the marker is excluded from dependency inputs.
`--previous` counts matching operations, rather than inferring hits from elapsed
time. Capture time is reported separately and excluded from replay measurements.
New captures also record each compiler process's elapsed time. These timings are
diagnostic and do not enter replay identities.

Copy the fixture outside this checkout to try edits. Changing only the application
source should preserve all library compilation markers. Changing `base` should
preserve `right` while rebuilding the affected branch. Adding or deleting package
resources also changes the corresponding package input.

Pass Cargo build options after `--`, for example `-- --features left/extra` or
`-- --release`. Use repeatable capture `--env KEY=VALUE` flags for environment
inputs, for example `--env RCE_LABEL=custom`. These are recorded in the plan;
recapture to change build options or environment. `--image` selects a toolchain
at capture time; its resolved digest is recorded. The default matches the
repository's pinned Rust SDK image. Diagnostic evaluation concurrency defaults
to eight. Add `--artifacts-only` to replay to demand and export the artifact
directory directly, without marker/digest queries or a report. This models the
artifact-returning path a Rust module would use; it cannot be combined with
`--report` or `--previous`.

Plans record the compiler invocations and graph, not source or build artifacts.
Replay reads the current package sources. Cargo manifests, lockfiles, `.cargo`
configuration, and toolchain files are fingerprinted: changes require recapture.
Keep plans, reports and exported outputs outside the source directory.

## Supported boundary

This first experiment supports Linux/amd64, path-only workspaces contained in the
source directory, and library/binary compilation. Incremental compilation is
disabled by default. An explicit native seed enables it for one named crate;
`--auto-incremental` enables automatic retention for all compiler actions.
Source resources must be regular UTF-8 files. Source inputs outside
their package roots, registry/git dependencies, build scripts, proc macros,
test compilation, custom targets and symlinks are rejected. `target` and `.git`
directories are excluded. Package inputs are deliberately coarse: every file
owned by the package participates in its cache identity.

The toolchain image must provide `/usr/bin/env` with `-u` support, as the default
Bookworm image does. Captured environment variables and removals are passed as
exec arguments instead of individual container configuration operations. They
still enter the cache identity, and literal values are never parsed as shell
source. An explicit removal takes precedence over a captured assignment.

This is a compiler replay experiment, not a replacement for normal Cargo builds.
Build-script execution, dependency downloads, proc macros and test execution are
the next stages. The capture wrapper forwards Cargo probes and normal compiler
diagnostics, and records successful compilations only. Replay rebuilds from an
empty target directory using native dependency files, without the capture's
build state. Compiler flags, relevant Cargo environment and `env!`/`option_env!`
dependencies enter the operation; jobserver and Dagger transport data do not.

The Go package under `replay` separates recipe construction from evaluation. Tests
can construct the same graph on different engines. Evaluation reads filesystem
outputs only: requesting a transferred container's private exec metadata could
rerun its compiler despite its artifacts already being available remotely.

## Performance work

The user-facing target is native Cargo time plus at most 0.5 seconds for an
equivalent command, including connection, source transfer, evaluation, output
transfer and process shutdown. A cached compiler operation alone does not meet
that target. The native backend, its integration into the Rust module, and the
module's command UX need separate measurements and end-to-end tests.

The backend remains unfinished. Automatic state selection and retention work
across captured crates, and the history Directory can be transferred to another
engine. Discovering the latest history automatically on a remote engine and
integrating the backend into the Rust module remain work to do. The native Cargo
controls enable incremental compilation, so disabling it cannot establish parity
on larger edited crates. Registry
dependencies, build scripts, proc macros and test actions also need support
before general module integration.

Replay reports separate source reading, connection, graph construction,
evaluation, export and native state retention. `driver.ready_seconds` stops when
artifacts and retained state are ready; it excludes report writing and process
shutdown. Per-action
`demand_seconds` includes Dagger's recipe and filesystem work as well as any
compilation, while `digest_seconds` measures the subsequent digest queries.

Use a prebuilt driver to measure full process time in independent CLI sessions:

```sh
go build -o /tmp/rcexp ./hack/rust-cache
python3 hack/rust-cache/benchmark.py \
  --source hack/rust-cache/replay/testdata/workspace \
  --plan /tmp/rust-plan.json --replay-bin /tmp/rcexp \
  --dagger-cli /tmp/dagger-rcexp \
  --out /tmp/rust-benchmark --runs 5
```

The benchmark warms results once, then checks that each measured command reuses
all compiler markers and preserves artifact digests. Its wall times include
shutdown and artifact export. Preparation and capture are excluded from warm
measurements. Logs, reports, artifacts and a summary are kept under `--out`.

Add `--artifacts-only` to the benchmark to time the artifact-returning command.
After each measured command, it compares exported bytes and permissions with
preparation, then runs a separate diagnostic command to verify every compiler
marker and digest. The summary stores that command under `verification`; its
time is excluded from the artifact-only measurement. A changed marker detects
a compiler rerun by either command. The default benchmark includes diagnostics
in the measured command.

For a native Cargo comparison, recapture with the current wrapper and add
`--cargo /path/to/cargo --rustc /path/to/rustc`. The script requires the captured
compiler version and matching Cargo version, uses the captured Cargo arguments
and environment overrides, and exits unsuccessfully if median replay overhead
exceeds `--budget` (default 0.5 seconds). Native Cargo retains its project/default
incremental setting; the summary records this difference from replay. These are
warm unchanged-build measurements. Source edits, realistic dependency graphs,
the Rust module itself, and remote-engine latency need additional comparisons.

Package sources are indexed once and directory recipes are reused across actions
in a package. Ownership lookup walks directory ancestors instead of scanning
every package. This removes the previous repeated workspace sorts and quadratic
package-root scans. Compare source grouping at 10, 100 and 300 packages with:

```sh
go test ./hack/rust-cache/replay -run '^$' \
  -bench '^BenchmarkPackageSources$' -benchtime=1x -count=3
```

Execution markers live in a small `/rcexp-meta` directory. On engines without
[#14555](https://github.com/dagger/dagger/pull/14555), a root-level marker can
trigger a walk of the entire toolchain filesystem. Dependency and exported
artifact bundles use `Directory.withFiles`, which benefits from
[#14557](https://github.com/dagger/dagger/pull/14557). Further engine changes
should follow measured bottlenecks and retain filesystem-only remote reuse.

The first performance pass on 2026-10-08 found:

- Source grouping at 300 synthetic packages with 16 files each took 9.68 seconds
  median with the old scan and 2.58 milliseconds with the index (three runs).
  This measures grouping, excluding directory recipes and compiler work.
- Five unchanged replays using the same Rust 1.77.2 compiler as native Cargo
  took 700 milliseconds median end to end, versus 14 milliseconds for Cargo.
  All compiler operations were reused. The 686-millisecond overhead failed the
  500-millisecond budget. Replay includes diagnostic marker and digest queries;
  the eventual module need not collect these on every build.
- Alternating fresh application edits before and after the marker change gave
  overlapping results around three seconds. They do not establish a consistent
  edit-latency improvement from that change on the tested engine.
- In a fresh capture, compiler-process times were approximately 112 milliseconds
  for the application and 19–22 milliseconds per library. These are capture
  measurements, not a paired Cargo/replay edited-build comparison.

These are tiny-fixture results on a shared host and the compatible development
image `localhost/dagger-go-taskforce:review`
(`v1.0.0-beta.15+5939a5d3.dirty`), not a general Rust performance claim. Source
grouping now scales better; cached-result demand, command startup/shutdown,
edited-build overhead and rustc incremental-state reuse remain work to do.

### wcprof follow-up

The next pass used engine and CLI source at `ea21cf49162d1eb9ae5749ea38813ee84cee7537`
on `main` (development version `v1.0.0-beta.17`), with the installed beta 16
runtime. This includes the merged file-checksum fix. The Rust driver was built
with that checkout's SDK. Both profiler engines were isolated from other work;
the underlying host was shared.

- A warm diagnostic replay issued 41 engine queries and traversed 821 cached
  `Container.withEnvVariable` calls for four compiler actions. Moving environment
  setup into exec arguments removed those calls. In nine alternating before/after
  runs, median graph evaluation fell from 125 to 83 milliseconds. All compiler
  markers were reused, and all 11 artifact digests matched the Cargo capture.
- Nine artifact-only commands took 535 milliseconds median versus 33 milliseconds
  for matched native Cargo. The 502-millisecond overhead still missed the
  500-millisecond budget. Exported contents, permissions and all compiler markers
  were checked after each measurement.
- Nine alternating runs per transport against the same warmed engine took
  535 milliseconds through Docker's exec tunnel and 429 milliseconds through
  direct loopback TCP. Compiler results were shared across transports. This
  isolates roughly 100 milliseconds of connection cost; it does not establish
  performance for remote TCP engines. Post-export time remained about
  290–310 milliseconds, so transport alone does not account for teardown.
- The artifact-only wcprof capture contained 26 engine queries across a
  66-millisecond interval, within a 477-millisecond full command. wcprof currently
  instruments queries and execs rather than the complete CLI lifecycle.
  Summed concurrent self times must not be treated as wall time.
- In the fresh app-edit capture before the environment change, the compiler
  process took 133 milliseconds and container runtime startup took 36 milliseconds.
  Only the application recompiled; the three library markers were reused.
  This is a phase breakdown, not a paired native Cargo edit benchmark.

The filesystem-only cache-transfer regression also passed against this `main`
engine: captured Cargo artifacts matched replay, source/resource/flag/environment
changes rebuilt the expected operations, and a second fresh engine reused all
four compilation markers from transferred filesystem parts.

A subsequent warm benchmark failed its reuse check after the engine pruned the
unchanged compiler results. Logs showed free-space-pressure pruning on the shared
host. The pruning target did not honor `reservedSpace` for `minFreeSpace` pressure;
the accompanying engine fix caps that target at cache usage above the reserve.
Regression tests reproduce both the incorrect target and removal of a cache
already below its reserve. This addresses retention, rather than warm query
latency. Keep the reuse checks enabled when benchmarking: byte-identical rebuilt
artifacts alone do not establish a cache hit.

With explicit retention on another isolated, unpatched `main` engine (4 GiB
reserved, 8 GiB maximum, `minFreeSpace: 0`), all nine artifact-only replays through
loopback TCP reused all compiler markers. Median full-command time was
684 milliseconds versus 21 milliseconds for matched Cargo: 663 milliseconds
overhead, still outside the budget. The shared host was under substantial I/O
pressure; this run is not comparable to the earlier alternating transport run.
Median artifact-ready time was 262 milliseconds and time after that was
432 milliseconds. A follow-up warm wcprof recording saw 26 queries over
76 milliseconds within a 506-millisecond command, with no compiler executions.
These measurements locate remaining work in the surrounding command lifecycle;
they do not establish edited-build or module-level parity.

### CLI lifecycle follow-up

Cloud export measurements found a 100-millisecond wait for the first trace batch,
followed by connection setup and requests that could remain on the shutdown path
of a short command. The CLI now flushes its first live Cloud span asynchronously
while connecting to the engine. Later batches and final shutdown keep their
existing policy; the initial flush has the Cloud request timeout. Commands without
Cloud export are unaffected.

- Nine alternating, uninstrumented diagnostic replays per implementation took
  511 milliseconds median before and 480 afterward through loopback TCP;
  through Docker they took 566 and 515 milliseconds. Compiler markers and all
  11 artifact digests matched on every run.
- Separate nine-run artifact-only comparisons with the change took
  477 milliseconds through TCP versus 35 for matched Cargo (442 overhead), and
  529 through Docker versus 35 for Cargo (495 overhead). Both met the
  500-millisecond budget for this tiny unchanged fixture. The Docker margin is
  small, and these separate runs do not measure the improvement by themselves.
- Seven fresh application edits through Docker took 601 milliseconds median
  versus 147 for matched Cargo (454 overhead). Each edit changed executable
  behavior; only the application recompiled, all three libraries were reused,
  and the replayed executable's output matched Cargo's. Replay ranged from
  530 to 1,145 milliseconds, so this median does not promise the budget on every
  edit. Native Cargo kept its default incremental setting; replay disabled it.
- In nine instrumented before/after pairs, Cloud span requests increased from
  19 to 22 total; log requests remained 18. Starting earlier can send an extra
  live update that would otherwise be coalesced. This is the cost of overlapping
  the first request with command work.
- Successful and failing commands still delivered their final root status,
  output, EOF records and execution metrics to a local OTLP receiver. A focused
  regression and its race run also verify delivery of completed spans when the
  initial request is blocked and the command context is canceled.
- Five alternating captures per transport located remaining Docker connection
  cost: 106 milliseconds median for connection versus 6 through TCP. Initial
  client creation and session setup each took about 40 milliseconds through
  Docker versus about 2 through TCP. These are diagnostic phase timings with
  an additional OTLP exporter, rather than an unprofiled latency comparison.
- A fresh-edit wcprof capture saw one compiler execution: 133 milliseconds in
  the compiler process and 38 in container runtime startup. Its 26-query window
  spanned 253 milliseconds within the 630-millisecond full command. The
  remaining command time includes connection and telemetry drain; concurrent
  query and wait totals should not be added to this wall-time breakdown.

This pass used the same `main` source and Rust toolchain as the wcprof follow-up,
with explicit cache retention on a fresh isolated engine. Keep the CLI pinned
with `--dagger-cli` or `_EXPERIMENTAL_DAGGER_CLI_BIN` when benchmarking. The helper
records its version and refuses an unpinned run, avoiding the SDK's download/PATH
fallback. Runs that selected another CLI or overlapped test compilation were
excluded. These tiny-fixture results do not establish performance for larger
edited crates, remote engines or the official Rust module.

### Larger edited crates

`benchmark_scale.py` generates many source modules inside one application crate,
with the same three path-library dependencies. It compares full artifact-only
commands with native Cargo using incremental compilation both on and off.
All builds use the same explicit codegen-unit count: Cargo otherwise changes
that default with incremental compilation, as described in the
[Cargo profile reference](https://doc.rust-lang.org/cargo/reference/profiles.html#codegen-units).
Each edited run uses a fresh random constant, recorded in the summary, so a repeat
on the same engine cannot accidentally measure a previously compiled edit.

The initial five-run comparison used 128 source modules with eight functions
each, 16 codegen units, Rust 1.77.2 and the same `main` engine/modified CLI as the
lifecycle pass. Median full-command times were:

| Scenario | Native Cargo, incremental | Native Cargo, full | Original replay |
| --- | ---: | ---: | ---: |
| Unchanged | 25 ms | 14 ms | 479 ms |
| One source-file edit | 487 ms | 2,341 ms | 4,149 ms |

Every edit changed executable behavior. All three library markers were reused,
and replay output matched both Cargo controls. The result shows two costs:
rustc's missing incremental state and avoidable source preparation.

A fresh-edit wcprof capture found 128 `Directory.withNewFile` snapshots taking
1.08 seconds before compilation. The flat recipe invalidated every subsequent
file after an early source edit. Source recipes now form a balanced tree with at
most 64 files per leaf. For an existing-file content or permission edit, unchanged
subtrees can be reused. File additions/deletions may also change the partitions.
The smaller sources retain their existing recipe.

A 16-file-leaf experiment reduced edited replay from 4.25 to 3.03 seconds in five
alternating pairs, but increased unchanged replay from 504 to 619 milliseconds.
The chosen 64-file leaves reduced rebuilt file snapshots from 128 to 30, with four
directory merges and six extra queries (32 versus 26). Its later wall-time runs
had substantial host-load drift and do not establish a reliable latency gain.
The filesystem regression checks nested paths, repeated basenames, empty/UTF-8
files, permissions and immutable old snapshots. The compiler regression now uses
a larger source tree and verifies filesystem-only reuse on a second engine.

Reproduce with a prebuilt driver and matching CLI; keep the generated workspace
and captures outside the checkout:

```sh
python3 hack/rust-cache/benchmark_scale.py \
  --dagger-cli /tmp/dagger-rcexp --replay-bin /tmp/rcexp \
  --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-scale --runs 5 --modules 128 --functions 8
```

### Native incremental snapshots

Replay can now enable rustc incremental compilation for one named crate. It
mounts a previous native `Directory` at `/rcexp-incremental` and retains the next
state through a persistable `Directory.withDirectory` operation. This is native
Dagger filesystem cache: rustc owns the state format and decides which internal
queries to reuse; Dagger owns the immutable snapshots and compiler-result cache.
No compiler `CacheVolume` is used.

```sh
# Prepare state once, then edit the source.
/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-artifacts --artifacts-only \
  --incremental-crate app --state /tmp/rust-state-before.json

/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-edited-artifacts --artifacts-only \
  --incremental-crate app --seed /tmp/rust-state-before.json \
  --state /tmp/rust-state-after.json
```

The state JSON contains a compatibility fingerprint and an engine-local result
handle, not compiler-state files. The handle remains usable while the engine
retains that result; it is not a portable reference or an automatic seed index.
The fingerprint excludes source contents and output digests, while keeping the
captured compiler configuration and dependency graph configuration fixed. A
different crate, toolchain, manifest configuration, flags or environment requires
new state. The seed is still an ordinary exec input: selecting a different seed
can change the result cache identity. The automatic-history mode below preserves
finished results through a separate native index before selecting a seed.

The fresh-engine regression exports the retained incremental `Directory` as a
separate native filesystem output root, alongside compiler outputs. Selecting a
compiler's root filesystem alone does not implicitly export its writable mounts.
The imported state keeps the same digest and seeds a subsequent edited build on
the second engine. This tests transfer of the state itself; the JSON's engine-local
handle is not transferred or reused on the second engine.

On the same 128-module fixture, five rotating-order fresh edits on the isolated
Docker engine produced these medians:

| Edited build | Full command |
| --- | ---: |
| Cargo, incremental | 535 ms |
| Cargo, full | 2,643 ms |
| Dagger replay, full | 3,496 ms |
| Dagger replay, native incremental seed | 1,723 ms |

Both replay variants reused all three libraries, recompiled the application,
and matched the behavior of both Cargo controls. State materialization and the
next reference write are included in the seeded command. The 1.77-second saving
is a comparison within this run, rather than against the earlier 4.15-second
baseline. The remaining median overhead versus Cargo incremental is 1.19 seconds.
On an eight-module smoke fixture, seeded replay was slightly slower than full
replay, so retaining state is not a universal win for small crates.

A fresh seeded-edit wcprof capture took 1.39 seconds overall, with 617 milliseconds
in rustc, 50 in runtime startup, and 30 rebuilt source-file snapshots. The query
window spanned 989 milliseconds. These are one diagnostic capture, not an additive
breakdown of the benchmark medians. Source import and command overhead still
need work. The measured source-construction cost belongs to `withNewFile`
snapshots, not filesync; compare native source-directory inputs before treating
it as a filesync implementation problem.

Reproduce the edited-build comparison by adding `--incremental` to
`benchmark_scale.py`. It only measures fresh edits; initial builds prepare and
verify the cache without serving as performance scenarios.

### Many-crate workspaces

The same helper accepts `--crates 100 --shape fanout` or `--shape chain` instead
of a multi-file application. It measures a leaf-library edit and a shared-library
edit separately. The fanout application depends on every leaf; each leaf depends
on the shared library. A leaf edit must compile exactly that leaf and the app,
while a shared edit must compile every action. The chain fixture uses the last
library as its editable leaf. Every edit changes executable behavior, and the
helper checks output against both Cargo controls and verifies execution markers.

Three runs with 100 fanout libraries (102 compiler actions) exposed a separate
scaling gap:

| Edit | Cargo incremental | Cargo full | Dagger replay, full |
| --- | ---: | ---: | ---: |
| Leaf library | 298 ms | 249 ms | 4,443 ms |
| Shared library | 903 ms | 812 ms | 24,403 ms |

A fresh leaf-edit profile recorded 911 engine queries while executing only two
compilers. Dependency and output assembly each expanded `Directory.withFiles`
into chains of individual `withFile` operations. A fresh shared-edit profile
took 19.47 seconds and showed an 8.82-second artifact-copy chain beneath export,
plus runtime-start contention (102 starts, 641 milliseconds median). Concurrent
query and runtime totals are not full-command wall time. These profiles identify
artifact assembly, repeated query work and execution concurrency as candidates
for the next experiments; they do not establish the benefit of an unimplemented
optimization. Larger chain workspaces still need performance measurements.

#### Balanced artifact bundles

Replay also accepts `--artifact-leaf-files 64`. Dependency and exported artifact
bundles split into a balanced tree with bounded `withFiles` leaves, joined with
native `withDirectory` snapshots. This shortens copy chains while preserving
file ordering and contents. Zero retains the original flat layout; the option
does not change source-tree construction or enable incremental compilation.

Three interleaved fresh edits per layout on the same 100-library fanout fixture
produced these full-command medians:

| Artifact layout | Leaf edit | Shared edit |
| --- | ---: | ---: |
| Flat | 4,040 ms | 19,719 ms |
| 64-file leaves | 2,755 ms | 7,218 ms |
| 16-file leaves | 2,196 ms | 7,233 ms |
| 64-file leaves, compiler demand limited to eight | 2,287 ms | 7,619 ms |

Each layout receives a different fresh source constant so it cannot reuse another
layout's newly compiled result. The helper rotates layout order, alternates Cargo
and replay order, and verifies compiler markers, exported bytes and permissions,
and executable behavior outside the timed commands. Cargo incremental medians
across layouts were 268–369 milliseconds for leaf edits and 718–790 milliseconds
for shared edits. Some individual Cargo runs spiked above two seconds; all samples
are retained. The 63% shared-edit reduction compares layouts within this run,
rather than using the earlier 24.4-second baseline.

A fresh 64-file shared-edit profile took 6.57 seconds overall. Export's critical
path was 1.12 seconds, including 1.01 seconds in file-copy snapshots, versus the
earlier flat profile's 8.91-second export. Runtime startup remained contended:
102 starts with a 582-millisecond median. Limiting filesystem demand to eight
reduced that per-start median to 66 milliseconds in a separate capture, but added
102 `File.size` queries and took 9.22 seconds overall. Lower concurrent phase
totals do not by themselves establish lower command latency. The demand limit
remains an opt-in experiment (`--compiler-concurrency 8`), not a selected
optimization. That initial demand experiment used artifact `File.size`; a
fresh-engine regression found that demanding this mount before the compiler's
root-filesystem marker could reexecute the app. The current demand helper uses
the same marker-first filesystem path as diagnostic evaluation. The timing
above describes the initial size-based experiment. Sixteen-file leaves did not
improve shared edits over 64-file leaves.

Reproduce the interleaved layout experiment using an existing many-crate capture:

```sh
python3 hack/rust-cache/benchmark_artifacts.py \
  --workspace-run /tmp/rust-fanout100 \
  --dagger-cli /tmp/dagger-rcexp --replay-bin /tmp/rcexp \
  --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-artifact-layouts --runs 3
```

`--workspace-run` must be a completed `benchmark_scale.py --crates` result.
This experiment edits that generated workspace and reuses its native Cargo target
directory. To benchmark one layout against both Cargo controls, pass
`--artifact-leaf-files 64` directly to `benchmark_scale.py`.

#### Direct compiler output snapshots

The next experiment, `--artifact-directories`, uses each compiler's existing
output-directory snapshot. That directory also contains its transitive inputs,
so dependents only need snapshots from their direct dependencies. Balanced
directory merges join independent branches. The final output combines terminal
actions, including independent workspace crates, and filters to the exact captured
artifact set. This removes repeated transitive graph walks, per-file projections,
and most artifact-copy snapshots. Compiler inputs also carry dep-info files in
this mode; the file-bundle variants exclude them. Both approaches still use native
immutable Dagger snapshots, with no compiler cache volumes.

Three further interleaved fresh edits on the same 100-library fanout fixture gave:

| Artifact layout | Leaf edit | Shared edit |
| --- | ---: | ---: |
| 64-file leaves | 2,113 ms | 9,292 ms |
| Direct compiler snapshots | 1,328 ms | 5,193 ms |
| 64-file leaves, marker-first compiler demand limited to eight | 2,983 ms | 10,812 ms |

The direct-snapshot improvement is 37% for leaf edits and 44% for shared edits
within this comparison. Cargo incremental medians were 265–519 milliseconds
for leaf edits and 1.02–1.25 seconds for shared edits. Individual Cargo runs still
showed substantial spikes; all results are retained. Do not combine percentage
gains from separate benchmark windows into one speedup claim.

A fresh direct-snapshot shared-edit profile took 4.08 seconds overall and issued
305 queries, versus 932 in the earlier 64-file profile. It executed all 102
compilers and used 101 directory-copy snapshots, with no `withFile` artifact-copy
chain. Export now demands the compilers lazily, so its 3.27-second critical path
includes compilation, unlike the file-bundle export phase. On that path, directory
copies accounted for 159 milliseconds; root-filesystem setup accounted for 1.04
seconds, runtime startup 637 milliseconds, base-spec generation 465 milliseconds,
and compiler processes 472 milliseconds. These are critical-path contributions
from one capture, not concurrent phase totals or a breakdown of the benchmark
medians. Runtime preparation is now the larger opportunity.

A subsequent three-run interleaved demand-limit comparison retained unrestricted
demand: direct snapshots took 1.20 seconds for leaf edits and 4.40 seconds for
shared edits, versus 1.59/4.83 seconds with a limit of eight and 1.58/4.67 seconds
with a limit of 32. Cargo shared-edit medians were 631–695 milliseconds. Reducing
startup contention through extra per-action requests did not improve the complete
command in either artifact representation.

With direct snapshots on the 128-module application, three rotating-order fresh
edits also preserved the incremental-state benefit:

| Edited build | Full command |
| --- | ---: |
| Cargo, incremental | 510 ms |
| Cargo, full | 2,293 ms |
| Direct snapshots, full rustc rebuild | 2,990 ms |
| Direct snapshots, native incremental seed | 1,099 ms |

Every edit recompiled the app, reused all three libraries and matched both Cargo
controls. Retaining the next state is included. The remaining median overhead
versus Cargo incremental is 589 milliseconds. A 24-library chain smoke run also
verified leaf and shared invalidation, artifact bytes and executable behavior;
one sample does not establish chain-workspace performance.

The focused fresh-engine regression checks direct snapshots and balanced file
bundles against captured Cargo artifact digests and the original assembled
directory. It also checks multiple independent terminal actions, transferred
compiler-result reuse, unchanged incremental-state digest after transfer, and a
subsequent edited build using that state. The remote transfer fixture establishes
correctness, not remote build latency.

Add `--artifact-directories` to `benchmark_scale.py`, with `--incremental` to
include the explicit seed variant. It cannot be combined with nonzero
`--artifact-leaf-files`. Use `benchmark_artifacts.py --variants balanced64 directories`
to interleave just these two layouts. The default interleaved comparison is flat,
64-file leaves and direct snapshots; optional demand limits remain experiments.

These remain synthetic workloads on Rust 1.77.2 with 16 explicit codegen units.
They do not establish performance for the official Rust module or real projects
with registry dependencies, build scripts, procedural macros or tests.

#### Engine experiment controls

`benchmark_artifacts.py` also accepts repeatable `--engine NAME=RUNNER_HOST`
arguments. It uses direct compiler snapshots on every engine and the same CLI
and replay binary, gives each engine a different fresh edit, rotates execution
order, and retains the normal Cargo, invalidation and artifact checks. Engine
comparisons cannot be combined with `--variants`. For example:

```sh
python3 hack/rust-cache/benchmark_artifacts.py \
  --workspace-run /tmp/rust-fanout100 \
  --dagger-cli /tmp/dagger-rcexp --replay-bin /tmp/rcexp \
  --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-engine-comparison --runs 3 \
  --engine baseline=docker-container://rust-baseline \
  --engine candidate=docker-container://rust-candidate
```

Further disposable engine experiments did not establish a useful shared-edit
latency improvement. A CPU profile attributed 13.9% of samples to snapshot-lease
synchronization, motivating one database transaction for a snapshot's retained
resources. An additional engine semaphore limited finite compiler executions to
eight. On freshly prepared engines, three rotating edits gave shared-edit medians
of 5.62 seconds for the baseline, 5.75 for transaction batching, and 6.47 for
batching with the execution limit. Cargo medians were 0.98, 1.02 and 4.03 seconds;
individual Cargo samples reached ten seconds, exposing substantial host noise.
These engine patches were not selected or added to this branch.

A separate three-run comparison tested sharing one sealed `runc` executable
within an engine. The disposable wrapper used runc 1.4.2's own executable-sealing
helper and verified its required seals; it did not disable the runtime's sealing
check. Leaf-edit medians were 1.071 seconds for the original runtime and 1.051 for
the shared executable. Shared-edit medians were 4.658 and 4.644 seconds, with Cargo
at 0.702 and 0.698 seconds. All invalidation, artifact and executable checks passed.
One profile showed less time in runtime startup, but complete-command latency
did not improve. This wrapper experiment was also not selected. Read-only source
mounts likewise failed to show a useful improvement in an earlier five-run trial.

The next substantial opportunities are automatic native incremental state,
importing native source directories instead of constructing per-file snapshots,
and reducing the entire compiler setup path, including root-filesystem and
specification preparation. Any seed-selection mechanism must preserve exact
result reuse and compiler compatibility; an ordinary seed mount still changes
the action identity.

Dependency scheduling has another unmeasured limitation. Cargo starts dependent
libraries once their dependencies' compiler metadata is ready, before machine-code
generation finishes, as described in the
[Rust compiler guide](https://rustc-dev-guide.rust-lang.org/backend/libs-and-metadata.html#pipelining).
Replay's dependency snapshots currently wait for the complete compiler execution.
A long-chain edited-build experiment should measure this lost overlap before
adding early output support or a separate metadata compilation pass, which could
duplicate compiler work.

Use an isolated engine with its debug endpoint enabled and a matching CLI.
Warm the workload before capturing it. The helper records the full command's
wall time and fetches the engine recording after completion, leaving captures
outside the workspace:

```sh
python3 hack/rust-cache/profile.py \
  --debug-url http://127.0.0.1:6060 --out /tmp/rust-warm-profile -- \
  /tmp/rcexp replay --source /tmp/rust-workspace \
  --plan /tmp/rust-plan.json --out /tmp/rust-profile-artifacts --artifacts-only
```

Repeat after a fresh source edit with a different capture directory. The helper
also captures failed commands and returns their exit status. Profiled wall times
are diagnostic; use unprofiled alternating runs to compare implementations.
Analyze `profile.ndjson` with the engine-lab `wcprof-report` helper built from
the same engine source. Start with `classes`, then `critpath` filtered to
`^session.serveQuery$`, and `waits`. The
[engine-lab workflow](../../.dagger/modules/engine-lab/skills/engine-lab/SKILL.md)
describes those views and their limits. Capture dumps and temporary CLI probes
are not committed.

### Native sources and automatic history

Use a prebuilt driver and keep the history reference outside the source tree:

```sh
/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-artifacts --artifacts-only --native-sources \
  --auto-incremental /tmp/rust-history.json
```

Run the same command after an edit. The reference file contains an engine-local
Directory ID and the history manifest's digest. Compiler outputs and incremental
state stay inside native Dagger snapshots. A missing or foreign local handle
falls back to an empty history; malformed reference files fail with an error.
The file is replaced atomically after the build and state retention succeed.
Concurrent writers can lose history updates, so use separate references for
independent build streams for now.

The index checks the compiler configuration, the actual package source digest,
and direct dependency keys before selecting incremental state. It retains four
finished versions per compiler action. Reverting a recent edit reuses the old
finished result even when the newest state came from another source version.
On a miss, the newest compatible state is an ordinary exec input. No input is
ignored in Dagger's cache key. Rustc decides which internal computations remain
valid. Diagnostic capture timings are excluded from compatibility fingerprints.

`--native-sources` imports one workspace Directory and projects package roots.
It preserves modes and excludes nested packages from their parents' inputs.
This removes the per-file `withNewFile` construction. The API accepts an existing
workspace Directory through `BuildOptions.SourceDirectory`; callers must supply
the same supported source/configuration snapshot and exclude `target` and `.git`.

`Graph.History` is the portable value: transfer its native snapshots and pass the
imported Directory to `BuildAutomatic` on the destination engine. The local JSON
ID alone is not portable. This prototype does not discover a shared remote
history index. Histories must come from this builder; a caller-supplied manifest
is not an authenticated compiler-cache record. Index pruning removes references
to old results; engine garbage collection controls their physical lifetime.

The latest three interleaved fresh edits of the 128-module application took 1.04
seconds median with automatic state and native sources, versus 2.75 seconds for
full native-source replay and 0.50 seconds for Cargo. Adding batching also took
1.04 seconds, providing no gain for the single compiler miss. All three libraries
stayed reusable. This is a local synthetic result on the shared host and the same main
engine/Rust 1.77.2 control described above, not a module or remote-latency result.

### Batching compiler misses

Add `--batch` to that command to run only the compiler misses in one container:

```sh
/tmp/rcexp replay --source /tmp/rust-workspace --plan /tmp/rust-plan.json \
  --out /tmp/rust-artifacts --artifacts-only --native-sources \
  --auto-incremental /tmp/rust-batch-history.json --batch
```

The runner starts at most eight rustc processes at once (`--batch-workers`).
Libraries can start when their dependencies announce completed metadata. Binaries
wait for the machine code of every transitive dependency. This follows
[rustc's documented pipelining](https://rustc-dev-guide.rust-lang.org/backend/libs-and-metadata.html#pipelining).
`--batch-no-pipelining` keeps the same execution and retention layout while
waiting for whole dependency compilations, providing a comparison control.

Each compiler searches a private target directory containing hard links to only
its captured dependency closure. Metadata is published before code generation
finishes; complete artifacts are published after success. Dep-info paths are
normalized back to `/target`. New source reads outside package ownership fail
the entire batch before history publication. These checks keep shared execution
from introducing dependencies absent from a crate's logical cache key.

The batch retains its output, incremental-state and marker trees once. Individual
index entries point into those native snapshots. This avoids copying every
crate's state through a separate result tree and multiple merge levels. A batch
failure publishes no successful history update. The runner binary and scheduling
options enter the history compatibility fingerprint.

This trades separate Dagger execs for one exec of the missed subset. The native
index still reuses completed results per crate, but losing that index loses this
per-crate lookup. Batching is optional; it is not a general engine optimization
or a change to Dagger's exec-cache semantics.

In three interleaved fresh edits of the 100-library fanout workspace:

| Edit | Full native-source replay | Automatic native batch | Native Cargo |
| --- | ---: | ---: | ---: |
| One leaf | 1.26 s | 1.13 s | 0.22 s |
| Shared dependency | 3.98 s | 2.13 s | 0.70 s |

Full-command times include state retention, source import, output export and
shutdown. Marker changes identified exactly two affected crates for leaf edits
and all 102 actions for shared edits. Executable behavior matched Cargo, and
exported bytes/modes matched separate verification exports. These runs do not
meet the Cargo-plus-0.5-second target.

The first batch implementation took 9.18 seconds for the shared edit. Its first
edited run spent 4.90 seconds retaining state. Grouped native snapshots reduced
that phase to 0.39 seconds in the first revised run. Automatic state with a
separate exec/result bundle per tiny crate regressed to 17.39 seconds median in
the earlier window. Retaining incremental state alone is not a workspace-wide
performance improvement; the many-crate layout matters.

Compare modes on an existing `benchmark_scale.py` fixture:

```sh
python3 hack/rust-cache/benchmark_artifacts.py \
  --workspace-run /tmp/rust-workspace-benchmark --replay-bin /tmp/rcexp \
  --dagger-cli /tmp/dagger-rcexp --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-batch-comparison --runs 3 \
  --variants directories_native directories_native_auto native_auto_batch
```

Capture records compiler start, completion and first metadata notification times.
`pipeline_report.py PLAN` reports Cargo's observed overlap and two compiler-only
dependency paths. `--batch REPORT` analyzes a batched replay's recorded misses.
The ideal paths ignore engine work and CPU limits; they are not predicted command
wall times. Generate deeper, heavier library chains with
`benchmark_scale.py --crates 24 --shape chain --library-functions 64`.

On that heavier chain, three interleaved shared edits took 1.86 seconds median
with pipelining and 2.04 seconds with it disabled, using the same incremental
state and batch layout. Cargo medians were 0.96 and 0.94 seconds, respectively.
One non-pipelined sample took 5.45 seconds and remains in the reported data;
the other two took about 2.04 seconds. A separate fresh-edit diagnostic recorded
24 dependent libraries starting before their producers completed, across a
1.07-second compiler window. The observed overlap confirms the scheduling works;
it does not remove the remaining command overhead.

A fresh shared-edit wcprof capture on the instrumented main engine recorded one
batch exec: 628 milliseconds in the worker, 51 milliseconds starting the runtime,
and 1.2 milliseconds across the newly measured root-filesystem mount phases.
Reading the retained history manifest had a 472-millisecond critical path,
mostly native copies; pruning one expired batch accounted for 346 milliseconds.
The corresponding full replay had 102 execs, with runtime-start durations around
494 milliseconds median under contention. Concurrent span totals are not wall
time. The batch has largely avoided that startup cost; history retention is now
an important remaining cost in this fixture.

Once an edit expires a single history batch, removing that directory from the
previous snapshot avoids rebuilding the whole retained tree through a filtered
copy. Three interleaved shared edits after four preparation versions took 1.95
seconds median with this removal versus 2.06 seconds with the filtered copy;
Cargo controls took 0.64 and 0.63 seconds. All six validation exports reused all
102 finished results and matched their timed exports byte for byte. A later
wcprof capture measured 341 milliseconds on the history-read critical path.
The whole-command gain is modest, despite the larger cost of the original copy.

The current batch writes artifacts, incremental state and execution markers into
one mounted native snapshot. History retains that snapshot directly, avoiding
the three directory joins previously used to collect outputs after compilation.
The exported artifact view contains only `target`; the worker removes its private
dependency hardlinks after all compilers finish. Inputs still include both the
selected seed and retained artifacts, and per-crate history keys remain separate.
The artifact directory is a view into that same snapshot, so retaining it also
retains the sibling incremental state. Filesystem export still selects only the
captured artifacts; remote transfer size and storage impact need measurement.

Initial fresh-edit measurements for this layout were inconclusive. An experiment
that removed only the final artifact copy took 1.08 versus 1.03 seconds for leaf
edits and 2.74 versus 3.06 seconds for shared edits. Cargo's shared-edit controls
ranged from 0.76 to 5.54 seconds as unrelated Go builds increased CPU and I/O
contention. A subsequent comparison of the unified layout was stopped under that
contention. Its completed leaf checks preserved all 305 captured outputs, their
permissions, executable behavior, and exactly 100/102 finished-result hits.
The profile still identifies the copy chain as work to remove; it does not
establish a full-command speedup.

The unified layout passed the full compiler replay integration scenario,
including edited builds after transferring native history to a fresh engine.
Its separate shared-edit profile reduced the history-read copy chain from five
operations to two (645 versus 296 milliseconds in these two captures). Overall
timings were still affected by other work. In the unified capture, artifacts and
history were ready after 2.407 seconds but the process took 5.044 seconds. Engine
logs attribute 2.448 seconds to flushing session Cloud telemetry before closing.
That is a separate end-to-end cost to investigate, rather than compilation or
snapshot persistence work.

Compare driver implementations on one isolated engine with fresh edits:

```sh
python3 hack/rust-cache/benchmark_artifacts.py \
  --workspace-run /tmp/rust-workspace-benchmark \
  --driver baseline=/tmp/rcexp-before --driver candidate=/tmp/rcexp-after \
  --dagger-cli /tmp/dagger-rcexp --cargo /path/to/cargo --rustc /path/to/rustc \
  --out /tmp/rust-driver-comparison --runs 5 --history-warmups 4
```

Each driver has its own history. Four preparation edits fill the bounded history
index before measuring expiry. The harness checks which crates recompiled,
finished-result reuse, exported bytes and permissions, and executable behavior
against Cargo; the diagnostic evaluations are outside the timed command. Linux
CPU and I/O pressure measurements are saved with the results. A timed automatic
build that loses its previous history now fails the comparison, rather than
being reported as a warm edited build.

Five rotating fresh edits per variant on an engine with Erik's merged
[read-only mount sharing](https://github.com/dagger/dagger/pull/14619), pinned to
`1fa708f7f`, gave these full-command medians:

| Edit | Earlier filtered layout | Unified snapshot | Direct history insertion | Cargo |
| --- | ---: | ---: | ---: | ---: |
| One leaf | 0.94 s | 0.85 s | 0.84 s | 0.21–0.22 s |
| Shared dependency | 1.84 s | 1.70 s | 1.68 s | 0.64–0.65 s |

Both compiler inputs and incremental history were warm; every source edit was
new. All 30 timed builds retained their histories. Leaf edits rebuilt two crates,
shared edits rebuilt all 102, and each subsequent validation reused 102/102
finished results and matched exported bytes, modes and Cargo behavior. These
synthetic local runs used Rust 1.77.2 and eight compiler workers on a shared host.
The unified layout improved medians by about 8–9% in this comparison. The smaller
additional differences from direct history insertion overlap ordinary variation.
The Cargo-plus-0.5-second target remains unmet. The direct insertion also passed
the full replay integration scenario, including edit reverts, history expiry and
an edited build after transferring native history to a fresh engine.

Direct history insertion puts the batch snapshot at its final history path,
removing the intermediate wrapping directory and its copy. A fresh shared-edit
wcprof capture confirms three directory copies instead of four. Runtime startup
took 40 milliseconds, while the history-read critical path took 186 milliseconds.
The previous unified capture recorded 117 query requests, including 102 package
digests, and 215 milliseconds constructing the driver graph. Reducing source-hash
requests and copying incremental inputs are the next experiments.

A separate five-pair engine comparison with the same unified driver found no
measurable benefit from mount sharing: medians stayed at 0.85 seconds for leaf
edits and 1.74 seconds for shared edits. One baseline sample took 19.98 seconds
after cache pruning removed its history and the Rust image was downloaded again.
That sample remains in the results; the newer warm-history check rejects this
case. Neither result establishes performance on remote engines or the cost of
transferring the unified snapshot's sibling incremental state.

To compare engine versions with the same native batch implementation, use
`--replay-bin /tmp/rcexp`, `--engine before=tcp://127.0.0.1:1234`,
`--engine after=tcp://127.0.0.1:1235` and `--engine-variant native_auto_batch`
instead of `--driver`. Keep compiler, worker count and cache policy identical on
both engines.

Longer edit sequences produced source-key changes for unchanged packages, but
the original trigger remains unresolved. The first proposed fix changed the
unused `internal/buildkit/cache/contenthash` package and cannot explain those
misses. The active importer uses `engine/contenthash`, which already saves its
records before publishing them to the memory cache. Ordinary eviction passes a
regression test against the real importer.

A separate restart repro found that the native snapshot checkpoint omitted
imported per-path hash records. Reopening the snapshot manager then rescans the
same files using SHA-256 instead of the importer's XXH3 hashes, changing directory
digests. The scoped fix saves the existing records for owned immutable snapshots
in the native checkpoint; filesync hashing is unchanged. The regression imports
real files and checks their digests after two SQLite checkpoint reloads. This
fix addresses restart stability; it has not been tied to the long-edit misses.
An independent test on main and the scoped fix also verified downstream action
reuse: the original action survives restart on both, but a previously untouched
identical source projection executes again only on main. That integration
regression fails on main and passes with the fix. The standalone
[test-only repro](https://github.com/grouville/dagger/tree/repro/native-contenthash-restart)
and [fix](https://github.com/grouville/dagger/tree/fix/persist-native-content-hashes)
are on the fork. The scoped fix is now
[draft PR #14622](https://github.com/dagger/dagger/pull/14622), following the
closed PR that changed the unused package.

Ten alternating clean-restart samples on a 20,020-file fixture missed 10/10
equivalent-directory actions on main and reused 10/10 with the fix. Median hash
plus action evaluation fell from 492 to 300 milliseconds; the full SDK probe
fell from 1.692 to 1.467 seconds, excluding Docker restart. The filesystem caches
and earlier actions were warm. These are synthetic restart measurements, not
Rust build speedups. The checkpoint added about 1.05 MB of hash records.
Cache-close medians increased from 637 to 686 milliseconds with overlapping
ranges; this is a noisy observation including other checkpoint work.

## Verify

```sh
go test ./hack/rust-cache/...
python3 -m unittest discover -s hack/rust-cache -p '*_test.py'
dagger api call engine-dev test --pkg ./core/integration \
  --run='TestRemoteCacheTransferSuite/TestRustCompilerReplay'
```

The integration scenario checks Cargo/replay artifact equality, executable
behavior, unchanged and edited builds, resource changes, feature/flag/environment
invalidation, and reuse on a second clean engine through the repository's remote
cache transfer fixture. Only the test infrastructure uses persistent volumes.
It also checks native source ownership/modes, automatic result reuse on edits
and reverts, stale local references, bounded history retention, batch dependency
visibility, rejected source reads, and native history transfer followed by an
edited build on the second engine.
