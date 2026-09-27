# Navigation and generation timings

With normal production Cloud telemetry, the generated file becomes available within **296 ms warm** and **379 ms after a new input edit** in this small native fixture. Full CLI exit remains **726 ms** and **925 ms** respectively. This clears the 500 ms target for file availability here, not for complete command exit or general SDK generation.

Current candidate engine with the existing experimental SDK stack; three ordinary repetitions per flow, unchanged CLI, retained caches. Five local correctness warmups and five separate diagnostic/profile commands are excluded from these medians.

| User operation | Ordinary samples (ms) | Median exit (ms) | Median file ready (ms) | Median file→exit (ms) |
| --- | --- | ---: | ---: | ---: |
| `dagger ws ls` — greetings-api | 633 / 547 / 615 | 615 | — | — |
| `dagger list -a` — greetings-api | 2332 / 2346 / 2320 | 2332 | — | — |
| `dagger generate -l` — greetings-api | 2119 / 2033 / 1733 | 2033 | — | — |
| `dagger -y generate` — native fixture, unchanged input | 730 / 726 / 722 | 726 | 296 | 430 |
| Unique input edit → `dagger -y generate` — native fixture | 925 / 904 / 1035 | 925 | 379 | 547 |

The native generator copies an ordinary workspace input into a generated output through a Changeset. Each measured edit uses previously unseen input bytes, and each generation starts with the output removed. Every resulting file exactly matched the current input. This is an actual user-facing generation command, but **not a Go/TypeScript SDK generator benchmark**.

All 25 commands passed. Workspace entries, artifact identities and generator identities were checked, listing output matched normalized local correctness runs, and both fixtures were restored. File availability uses 5 ms polling; full exit uses blocking waitpid.

## Separate diagnostics

Each row below is one instrumented/profiled invocation, not part of the ordinary median. The shutdown phases are nested: do not add engine close to shutdown HTTP, or telemetry close to provider shutdown.

| Flow | CLI exit (ms) | Query union (ms) | After command callback (ms) | Engine shutdown HTTP (ms) | CLI telemetry close (ms) | CLI HTTP uploads |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| workspace-files | 591 | 28 | 427 | 160 | 242 | 5 |
| artifacts | 2337 | 1391 | 781 | 609 | 134 | 6 |
| generators | 1632 | 632 | 848 | 668 | 149 | 7 |
| generate-warm | 836 | 138 | 547 | 370 | 153 | 6 |
| generate-edit | 833 | 223 | 421 | 240 | 156 | 6 |

The complete numeric phase breakdown, exact samples, HTTP counters and allowlisted operation-class aggregates are in `analysis.json`. All five wcprof files report zero open operations and zero dropped events. Request counts include only exact `cloud.traces`, `cloud.logs` and `cloud.metrics` HTTP rows; exporter wrapper spans are excluded.

The 5 local warmups are setup/correctness evidence, not a controlled production-versus-local benchmark. These retained-volume measurements make no cold-start claim. Raw outputs, wcprof string tables and payloads remain private. CPU, I/O and operation durations overlap with wall time and cannot be added as hypothetical savings.
