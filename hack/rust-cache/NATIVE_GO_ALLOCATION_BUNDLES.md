# Allocation reductions and concurrent client admission

Neither combination establishes faster Go collection listing. Both remain disabled. The latest comparison measures **38.62 → 39.54 seconds median**, with two improvements and two regressions. Lower allocation alone has not delivered the required command latency.

The command is `dagger check --module go --check test --list --all`, against dagger/dagger `ff0b029a` and the selected Go module `7568cd0`. Every invocation starts a fresh CLI and receives a fresh source comment on the same warm engine and volume. Telemetry, ordinary garbage collection, native cache keys, collection granularity and cleanup remain enabled. Profiling and diagnostic counters are off during timing. Cold startup is unmeasured; the local telemetry receiver does not model Cloud latency.

## Fixed experiments

The first candidate combines four existing changes: reuse prepared schemas and callback scopes, create type maps on demand, and reuse interface field lists during each reconciliation pass. Their individual complete-command results were inconclusive. This cohort tests their combined effect.

The second candidate adds concurrent admission for distinct clients. Its hypothesis is that lower allocation pressure could make that concurrency useful. The two studies use separate fixed cohorts; their gains cannot be added or assigned to individual switches.

| Four measured pairs; separate column medians | Four allocation changes | Allocation changes plus concurrent admission |
| --- | ---: | ---: |
| Complete command, control → candidate | 39.89 → 36.26 s | 38.62 → 39.54 s |
| Faster pairs | 2/4 | 2/4 |
| Cumulative allocation | 29.65 → 25.85 GB | 29.66 → 26.68 GB |
| Engine CPU | 197.46 → 180.86 CPU-seconds | 195.22 → 191.73 CPU-seconds |

Allocation is cumulative, not peak memory. CPU totals include concurrent work and are not elapsed time saved.

| Pair | Allocation control | Allocation candidate | Admission control | Admission candidate |
| --- | ---: | ---: | ---: | ---: |
| 1, candidate first | 38.96 s | 34.24 s | 35.38 s | 37.54 s |
| 2, control first | 40.81 s | 34.07 s | 47.86 s | 41.54 s |
| 3, candidate first | 43.82 s | 45.58 s | 36.80 s | 34.87 s |
| 4, control first | 37.54 s | 38.28 s | 40.44 s | 48.74 s |

Each study also retains an excluded initialization pair that adds a real test and returns 4,399 rows. Measured pairs remove that test and return the same ordered 4,398 rows. All twenty commands exit successfully through cleanup. No attempt is dropped because maintenance overlaps it. In the allocation study, candidate pair 3 overlaps a class-table compaction from 1,127,195 to 644,368 slots. In the admission study, control pair 2 drops from 845,817 to 679,610 slots, and candidate pair 4 from 775,682 to 699,134. These overlaps prevent attributing the full variation to the switches.

## Correctness and selection

Both combinations pass the existing Go collection and package-layout rebinding checks. Those checks exercise edited inputs and retained package objects. With each combination enabled, all six retained Rust histories reuse every compilation action before and after its cohort: **130/130, 1,026/1,026 and 6/6**, twice each.

The four-change cohort uses engine `00166f29`; the admission cohort uses `695ad854`, which adds profiling-only HTTP parent propagation. Profiling is off throughout both timing cohorts. Both retain CLI `e7ba08d0`, the same source and module revisions, and every selected optimization.

All five switches are restored off. Source and configuration are restored. The primary Rust timing manifest is unchanged. These experiments add no upstream proposal or PR. The subsequent [compaction candidate](NATIVE_CACHE_COMPACTION_DIGEST_SETS.md) brings the review queue to eighteen Dagger descriptions and one Go-module description.

[Allocation study evidence](experiments/go-allocation-bundle/) and [admission interaction evidence](experiments/go-admission-allocation-bundle/) retain the exact drivers, source context, all observations, checks and final selection. [The causal profile](NATIVE_GO_QUERY_ATTRIBUTION.md) identifies the remaining waits.
