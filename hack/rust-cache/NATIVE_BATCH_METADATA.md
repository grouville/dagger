# Reuse telemetry metadata within each batch

Reusing repeated resource and instrumentation-scope metadata makes the expanded 1,026-package listing consistently faster. All sixteen edited pairs improve across the initial comparison and swapped-history confirmation. The confirmation decreases median command latency from 5.28 to 4.08 seconds and median engine-container CPU use by about 40%. Ordinary edited compilation and test latency remain mixed; this does not close the gap with Cargo.

The two standalone commits are on Guillaume's fork: [span metadata](https://github.com/grouville/dagger/commit/9b0114d9b) and [log metadata](https://github.com/grouville/dagger/commit/74ad814fc), based on main `6de2877bc`. No PR is open.

## Change and correctness

The telemetry readers previously parsed the same resource and scope JSON for every row. The span converter also requests some metadata more than once per span. The new path decodes each distinct value once within a batch, then reuses immutable decoded metadata. Every span and log record still carries its own IDs, attributes, timestamps and body. The maps live only for that conversion call: there is no global cache, new lock, dependency or persistence format.

Span grouping still uses the existing converter. Log grouping preserves its existing resource, scope and schema behavior. Exported protobuf groups retain independent mutable metadata: re-reading the prototype exposed an alias between two groups, fixed with a clone when creating a group. The regression fails without that protection. Invalid log metadata remains a per-record failure; failed decodes are not cached.

The complete client database suite and focused server tests pass under the race detector. The latter exercise export ordering, retries, oversized batches, malformed input and draining after teardown. Tests compare span exports with the original converter and cover different resources/scopes, equivalent resource JSON, different schema URLs, invalid rows, subsequent batches and protobuf ownership.

After a clean engine restart, both histories preserve their compiled results. The probe's used Rust edit rebuilds exactly two of 1,026 actions. After both benchmark cohorts and the subsequent edited-build profiles, all six histories again reuse every action: 130/130, 1,026/1,026 and 6/6. Compiler results and incremental state remain native Dagger snapshots.

## Conversion cost

Five-sample component medians use Go 1.26.6, `GOMAXPROCS=8` and the selected attribute-array decoder in both variants. No other build or profile runs during timing. The original span benchmark preallocates its wrapper slice, matching the original server call.

| Conversion | Original | Candidate | Original/candidate allocated bytes | Original/candidate allocations |
| --- | ---: | ---: | ---: | ---: |
| 512 spans | 4.00 ms | 2.14 ms | 1,447,895 / 914,041 | 33,881 / 18,488 |
| 512 logs | 3.74 ms | 1.89 ms | 1,148,807 / 608,992 | 30,215 / 14,886 |
| One log | 7.37 µs | 7.97 µs | 2,441 / 2,665 | 63 / 66 |

The single-record log case costs about 0.6 µs more. The maps can contain as many distinct entries as the input batch; the benefit depends on repeated metadata.

A separate real-command counter probe observes 71,679 span-row and 58,614 log-row conversions, with only 229 resource decodes and 325 scope decodes. This counts conversions across readers, not unique emitted records. It prints the exact 1,026-package set. Counters are disabled for every timed comparison.

## Complete edited commands

Both arms use the same warm engine and binary, module `30600fd`, the buffered CLI and the selected attribute-array decoder. Only per-batch metadata reuse changes, through a diagnostic switch outside the timer. Telemetry stays enabled. Wcprof, diagnostic counters and immutable source-import seeds are off. Each invocation edits a used Rust value; order rotates. Cargo uses Rust 1.77.2 with incremental compilation. All listing outputs must contain the exact expected package set.

Eight initial pairs:

| Command | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Check, 130 crates | 0.699 s | 0.698 s | 0.121 s | −17 ms | 3/8 |
| List, 1,026 packages | 5.003 s | 4.427 s | 0.442 s | 737 ms | 8/8 |
| Grouped check, 1,026 crates | 2.413 s | 2.537 s | 0.805 s | 76 ms | 5/8 |
| Small workspace tests | 1.075 s | 1.053 s | 0.511 s | −5 ms | 4/8 |

The confirmation swaps the physical native-cache histories and measures the two large-workspace commands for eight more pairs:

| Command | Original median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| List, 1,026 packages | 5.280 s | 4.078 s | 0.458 s | 1,293 ms | 8/8 |
| Grouped check, 1,026 crates | 2.461 s | 2.393 s | 0.810 s | 59 ms | 5/8 |

The confirmation also reads the owned engine container's cgroup CPU counter outside each wall-time interval. Listing medians decrease from 20.27 to 12.23 CPU seconds, with lower CPU use in seven of eight pairs. Grouped-check medians decrease from 2.152 to 2.005 CPU seconds, also seven of eight. These counters cover work charged to that cgroup during the command; they are not elapsed time or an attribution to an individual Go function.

All observations remain included. Admission requires an idle engine and a one-second low-I/O window before an invocation, without filtering afterward. Initial maximum host/engine I/O pressure reaches 39%/24%; confirmation maxima are 9.5%/8.8%. Candidate outliers of 25 and 29 seconds remain in the data. The repeated listing improvement and lower CPU consumption are established on this workload. The five-of-eight check results do not establish a general edited-build latency improvement.

The shared local OTLP sink is `hack/otlpdump`: it serializes and writes JSON records under a mutex before acknowledging a request. Its capture file has grown to 62.55 GB. Both arms use that same sink, but recording can add CPU and disk work outside the engine cgroup. The long outliers are not yet diagnosed as engine regressions. A separate counting-only OTLP receiver would help bound observer overhead while keeping telemetry emission enabled; the existing captures must remain available for trace inspection.

## Next compilation bottleneck

Two fresh edited checks collect complete wcprof traces and CLI CPU/runtime profiles, with zero dropped events and zero open operations. These profiled commands are diagnostic observations, not additional benchmark pairs.

For 1,026 crates, the main query takes 2.37 seconds. Source import occupies 444 ms, followed by a 688 ms `Rust.packages` call; `Check.sync` then occupies about 1.19 seconds. The source import and discovery together therefore consume roughly 1.13 seconds before the check. `dang.invoke` includes nested API waits and compiler execution, so its duration is not interpreter CPU time.

The module's `packages` method runs `cargo metadata --offline --no-deps` with the complete source directory mounted. A Rust content edit changes that execution's input even when the workspace package names remain the same. The next experiment should reuse discovery across those edits while preserving changes to manifests, configuration, workspace membership and automatic target discovery. The existing native compiler-plan configuration guard is a possible building block, but its suitability for package discovery still needs verification.

Source-import snapshots remain a separate measured experiment with storage/transfer work pending. They are deliberately off in both arms here. The ordinary check's candidate median remains 2.39 seconds versus Cargo's 0.81 seconds, above the target. Registry dependencies, general build scripts, procedural macros and remote automatic state discovery remain unfinished for the native backend.

Evidence and local harnesses: [batch-metadata](experiments/batch-metadata/). Raw CLI runtime traces remain under `/tmp/rust-cache-sipsma-review/batch-metadata-edited-check-profile`. The production branch contains no diagnostic switches or counters.
