# Read compiler-plan metadata through file transfer

After grouping package hashes, two fresh 1,026-crate captures spend 113–116 ms reading the retained plan through `File.contents` and another 35–36 ms decoding its JSON. The plan is about 2.5 MB. The [isolated variant](https://github.com/grouville/dagger-rust/commit/a6143eb) exports the same metadata file into a private temporary directory in the Go module, reads its bytes and removes the directory. It makes the temporary copy readable independently of the source mode. JSON decoding and the existing automatic recapture/error behavior remain in `Compile`.

Compiler results and incremental state remain native Dagger snapshots. This transfers only plan metadata that the previous implementation already read into Go memory. It does not retain local state across commands, add an engine API or disable telemetry. The variant remains unselected because its initial command benefit does not survive the history swap.

## Complete edited commands

The control is `28dab90`. Both variants run on one warm engine with grouped hashes, the primitive-array ownership fix and content-keyed syntax. Diagnostic lease instrumentation is present but wcprof is off. Each variant has separate sources and native history. Every command has a fresh, distinct edit. Rust 1.77.2 uses eight jobs; order rotates with Cargo. Telemetry stays enabled, timing uses blocking process exit, and two preparation rounds are excluded. No unrelated build or test runs during timing.

| First eight pairs | Plan text | Plan file | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf | 0.684 s | 0.667 s | 0.098 s | 12 ms | 5/8 |
| 130 crates, shared | 1.356 s | 1.308 s | 0.620 s | 42 ms | 5/8 |
| 1,026 crates, leaf | 2.136 s | 2.053 s | 0.769 s | 78 ms | 7/8 |
| Actual package test collection | 1.010 s | 0.998 s | 0.484 s | 3 ms | 6/8 |

The implementations are then swapped between those same histories, without restarting the engine. Two preparation rounds precede eight more pairs:

| Histories swapped | Plan text | Plan file | Cargo | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130 crates, leaf | 0.710 s | 0.740 s | 0.110 s | 15 ms | 5/8 |
| 130 crates, shared | 1.436 s | 1.531 s | 0.628 s | −26 ms | 4/8 |
| 1,026 crates, leaf | 2.638 s | 3.393 s | 0.777 s | −83 ms | 3/8 |
| Actual package test collection | 1.126 s | 1.251 s | 0.503 s | −155 ms | 3/8 |

Host I/O stalls reach 20.4% and 64.0% in the two series; engine I/O stalls reach 0.74% and 37.5%. The crossover retains all slow samples, including a 6.856 s candidate large edit, 8.665 s control shared edit and 4.513 s Cargo shared edit. The candidate's small collection slows too. These results do not establish a general benefit or attribute the tails specifically to file transfer. No size threshold is selected.

The integration passes under race detection for exact Unicode/escaped JSON, a 1.3 MB multi-chunk file, missing files, read-only source mode and temporary cleanup. An original-history bridge reuses 1,026/1,026 results. After timing, both histories recover all 130, 1,026 and six results, with exactly 130 shared-edit, two large-leaf and four application-test execution markers.

The [measurements](experiments/native-plan-file-transfer/measurements.json) retain both timing series, pressure and correctness outcomes; drivers are archived beside them. The tested experiment is pushed to the fork for reproducibility, with no default change or PR.
