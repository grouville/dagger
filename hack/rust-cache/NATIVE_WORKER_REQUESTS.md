# Smaller worker requests on the current native Rust stack

Sending only the dependency fields the worker reads improves the complete edited check at 1,026 crates in 15 of 16 pairs across two cache histories. The implementation adds seven lines and removes one. Keep it as the next experimental native-cache baseline; the official module's native backend remains opt-in.

Code: [e63b6a2](https://github.com/grouville/dagger-rust/commit/e63b6a2a942fc62835f6ec1d20eb4f3566125490), based on `cd6d25e`, on `experiment/native-worker-request-current`. This reapplies [a6e77f8](https://github.com/grouville/dagger-rust/commit/a6e77f8c9cbb4b077442daea6814507051e0fa19). The earlier 203-action experiment did not establish a command gain; the larger workload and current stack justify this separate confirmation. No PR is opened.

Every compilation that executes still receives its complete command and environment. The separate dependency table supplies only IDs, output paths and dependency edges, which prepare the compiler's private artifact view. Previously that table repeated complete commands, environments and capture measurements for every action, including unchanged ones.

| Actual captured plan | Actions executed for the edit | Request bytes before | Request bytes after |
| --- | ---: | ---: | ---: |
| 130 actions | 2 | 294,417 | 69,589 |
| 1,026 actions | 2 | 2,301,321 | 524,776 |
| Small workspace, 6 actions | 4 | 18,800 | 9,444 |

The large request shrinks by 77%. The worker source and binary, compiler commands, result keys, seed compatibility, cache manifest and native snapshot retention are unchanged. The execution's request-file contents change; existing per-crate results remain reusable through the separate native history.

## Complete edited commands

Each series has eight pairs per scenario, with rotating baseline/candidate/Cargo order. Every invocation changes a used Rust value and starts a fresh CLI and helper process. The engine and Rust caches are warm. Each implementation has its own existing physical history; the confirmation exchanges the implementations between those histories. Two preparation rounds precede each series. All admitted observations remain included.

Both arms use engine SHA-256 `a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa`, source snapshot seeds, compact scalar restoration, batch telemetry metadata reuse and the attribute-array decoder. Telemetry stays enabled with the same decoding/null receiver. CPU/block sampling and wcprof are off during timings. Cargo uses incremental Rust 1.77.2 and eight workers.

| Series | Edited command | Before median | Candidate median | Cargo median | Median paired saving | Faster pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Paired | 130-crate direct check | 0.655 s | 0.631 s | 0.129 s | 11 ms | 5/8 |
| Paired | 1,026-crate collection check | 1.770 s | 1.625 s | 0.790 s | 192 ms | 7/8 |
| Paired | Small collection tests | 1.009 s | 1.006 s | 0.494 s | -3 ms | 4/8 |
| Crossover | 130-crate direct check | 0.643 s | 0.624 s | 0.127 s | 22 ms | 6/8 |
| Crossover | 1,026-crate collection check | 1.689 s | 1.521 s | 0.783 s | 184 ms | 8/8 |
| Crossover | Small collection tests | 0.995 s | 0.982 s | 0.483 s | 9 ms | 5/8 |

The gain is clearest on the large workspace. The small collection does not establish a repeatable benefit. Column-median differences and medians of paired differences are distinct statistics.

Every launch requires an idle engine and a one-second window below 5% host and 1% engine I/O stalls. Stalls after admission do not exclude a sample: measured host I/O pressure reaches 5.31% in the first series and 20.05% in the confirmation; engine maxima are 3.66% and 1.02%. All slow observations remain included.

The first large-check engine-cgroup CPU medians are 1.651 s before and 1.844 s after, despite a 78 ms median paired CPU saving. The crossover medians are 1.646 s and 1.450 s, with a 196 ms paired saving. This counter includes concurrent engine work but excludes sibling helper/compiler cgroups; see the [accounting clarification](CPU_ACCOUNTING.md). These results support the latency improvement without establishing total Dagger CPU savings.

In the confirmation, median paired candidate-minus-Cargo overhead is 0.519 s for the direct check, 0.744 s for the large check and 0.495 s for small tests. Only 3/8, 0/8 and 4/8 corresponding pairs are within Cargo +0.5 s. The complete performance target remains unmet.

## Correctness and tradeoff

The main package compiles, and model, replay and worker suites pass with the race detector. Actual module calls verify an empty 130-action cache, complete reuse, a used-source edit retaining 128 results, invalid Rust rejection, repair and reversion. Before and after measurements, all six existing histories reuse 130/130, 1,026/1,026 and 6/6 results, with the expected previous batch markers.

The change adds a temporary action slice proportional to plan size and reduces the much larger serialized request and its subsequent copies. It introduces no API, lock, shared state or dependency. Existing worker tests exercise dependency views with the required fields; actual compilation checks cover the producer/consumer contract. No implementation-mirroring test is added. Future worker changes must preserve or explicitly extend the dependency-field contract.

The [helper profiles](NATIVE_HELPER_CPU.md) provide separate diagnostic evidence: two large captures per implementation contain 420 ms of sampled process CPU in total before and 290 ms after. This small profile set localizes work; the unprofiled commands above establish the latency result.

Evidence, exact payload plans, source patch, correctness logs and drivers: [worker-request-current](experiments/worker-request-current/).

The next [deep-workspace baseline](NATIVE_TRANSITIVE_ARTIFACTS.md) also avoids rebuilding transitive output lists in the batch path, while retaining this compact request representation.
