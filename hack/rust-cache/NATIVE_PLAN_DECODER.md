# Faster plan decoding: promising component, mixed command results

Keep `f73c561` as the native Rust baseline. The [isolated decoder experiment](https://github.com/grouville/dagger-rust/commit/9fc8a74) reduces first-use decoding of the 1,026-action plan from 65 to 11 ms, but two complete-command comparisons disagree on the large-workspace benefit. That is insufficient evidence to select a new dependency.

The helper still reads the complete captured plan on each edited command. The measured file is 2,528,109 bytes, including 972,644 bytes of action environments; 21 environment entries are common to every action. Avoiding repeated data remains a separate opportunity. This experiment changes only incoming plan decoding. Canonical JSON encoding, compiler commands, native result keys, seed selection and the cache format use the preceding code.

## First use, including decoder initialization

Six rotating comparisons use a fresh process per observation, identical plan bytes and Go 1.26.6 with `GOMAXPROCS=8`. Each decoder is timed on its first call. Reference decoding, deep equality and canonical-encoding checks run afterward. The surrounding process timer also includes that validation and is not a startup benchmark.

| Decoder, 1,026-action plan | Median decode | Allocated bytes | Allocations | Faster than standard |
| --- | ---: | ---: | ---: | ---: |
| `encoding/json` | 65.34 ms | 7.71 MB | 130,848 | — |
| `goccy/go-json` v0.11.2 | 11.07 ms | 8.66 MB | 9,201 | 6/6 |
| `segmentio/encoding/json` v0.5.4 | 44.98 ms | 10.51 MB | 96,251 | 5/6 |

The 130-action medians are 11.93, 4.27 and 7.03 ms respectively; the six-action medians are 1.90, 0.67 and 0.23 ms. The alternative decoders allocate more bytes on these inputs despite fewer objects. These measurements select a candidate for a real-command experiment; they do not establish complete-command savings.

The exact packages are [go-json v0.11.2](https://github.com/goccy/go-json/tree/v0.11.2) and [segmentio encoding v0.5.4](https://github.com/segmentio/encoding/tree/v0.5.4). Their compatibility claims are checked against the actual typed plans rather than assumed.

## Complete freshly edited commands

Both implementations use the same owned engine, telemetry receiver and native snapshots. CLI and helper processes are fresh; engine and compiler state are warm. Each cohort contains eight rotating baseline/candidate/Cargo pairs per workload. The confirmation exchanges implementations between the two physical histories. Two preparation rounds are excluded, profiling is off, and all admitted observations remain included.

| Workload | First cohort, before → candidate | Confirmation, before → candidate | Faster pairs, first / confirmation |
| --- | ---: | ---: | ---: |
| Direct check, 130 crates | 0.606 → 0.586 s | 0.620 → 0.604 s | 5/8 / 4/8 |
| Collection check, 1,026 crates | 1.644 → 1.728 s | 1.574 → 1.545 s | 3/8 / 7/8 |
| Small collection tests | 0.987 → 0.979 s | 0.958 → 0.956 s | 4/8 / 5/8 |

For the large check, the median paired saving is -79 ms in the first cohort and +65 ms in the confirmation. Cargo medians are 0.768 and 0.772 s. The complete Cargo +0.5-second target remains unmet. Small cases establish no consistent material improvement.

Admission requires no active session and a one-second window below 5% host and 1% engine I/O pressure. Later stalls are retained: two candidate observations take 15.513 and 17.616 seconds. Maximum host I/O pressure reaches 26.2% and 39.1% across the two cohorts; engine maxima are 8.8% and 1.9%. Thus host and engine variance remain material. The candidate's first module preparation takes 17.229 seconds; the preceding module is already prepared, so this is not a matched cold-start comparison.

## Correctness and remaining bottlenecks

The candidate's model/replay/worker suites pass under the race detector. Differential checks cover nulls, duplicate keys, malformed strings, Unicode, unknown fields and type errors. A 30-second fuzz run executes 651,586 cases without differing successful values or error presence. This is useful coverage, not proof of universal decoder equivalence.

Worker, wrapper and test-recorder binaries are identical between the two source trees. Through the actual module, a new 130-action history has 0 hits, a used-source edit has 128, invalid Rust fails, and repair and reversion each recover all 130 results. All six earlier histories also reuse 130/130, 1,026/1,026 and 6/6 results.

Six separate wcprof captures have no dropped events or open operations. One candidate command has a 1,286.55 ms source import, compared with roughly 166–178 ms in the other captures. A stack taken while that command is active also shows containerd snapshot cleanup running. The foreground query is runnable in cache lookup, so the stack does not establish a direct wait on the collector. Neither original 15–18-second stall is reproduced by these six captures.

The 25-second engine CPU profile includes 3.58 cumulative sampled seconds through session GC and 2.54 through containerd snapshot cleanup. These scopes overlap and include background work; they are not additive command overhead. A [controlled follow-up](NATIVE_GC_CONTENTION.md) now establishes that concurrent accounting and collection can slow edited commands, while leaving the cause of these particular pauses unproven. The new dependency remains isolated pending stronger complete-command evidence.

[Evidence and reproducible drivers](experiments/plan-decoder/) include exact plans, first-use observations, both full-command cohorts, compatibility/fuzz logs, native reuse checks, wcprof traces, goroutine stacks and engine CPU data. Paths and receiver addresses need adjustment elsewhere. No PR is opened.
