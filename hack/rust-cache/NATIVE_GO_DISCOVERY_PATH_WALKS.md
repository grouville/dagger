# Reduce Go discovery work without changing collection behavior

These experiments keep the complete flow: current workspace discovery, normal collection getters, selection, real test execution, native source snapshots, telemetry and session cleanup. Removing redundant work is acceptable only when that flow still behaves correctly and the complete command improves.

## Batch module-header reads: not selected

The shared Go library currently reads each discovered module's `go.mod` separately. A candidate searches the known files together, validates full matched lines with the existing header expression, and retains the original reader for unconfirmed paths or search errors. JSON search results preserve paths containing newlines. Ownership and collection getters are unchanged.

| Complete-command median | Original reader | Batched positive headers |
| --- | ---: | ---: |
| Test-file edit | 9.36 s | 9.28 s |
| Ordinary-source edit | 6.13 s | 5.93 s |
| Test-file edit, engine CPU | 47.25 CPU-s | 46.48 CPU-s |
| Ordinary-source edit, engine CPU | 28.91 CPU-s | 26.22 CPU-s |
| Test-file edit, allocated bytes | 10.01 GB | 9.82 GB |
| Ordinary-source edit, allocated bytes | 5.17 GB | 5.03 GB |

All four source-edit pairs improve, but only two test-edit pairs do. One slow control test-edit command takes 12.13 seconds; it is retained. The median paired test-edit saving is only 0.05 seconds. This does not justify selecting the added search and fallback logic.

The profiles confirm that the candidate actually removes the per-file reads: 80 `Workspace.file` executions become zero, replaced by one additional search. SDK requests fall **1,494 → 1,415** after test edits and **572 → 493** after ordinary-source edits. Test-edited captures still perform **804 module evaluations and all 800 getter executions**, with 799 unchanged test-discovery hits. Ordinary-source captures retain three evaluations and all 800 getters and discoveries hit. All four captures are lossless, with no open operations or dropped events. Diagnostic capture durations are not additional latency samples.

Thirteen focused checks pass, including header variants, binary input, newline paths, existing symbolic-link read errors, overlays, module boundaries, non-root discovery, custom tool settings, selection, test execution, binary construction and generation. All 24 timing commands have correct ordered names, identical full rows and successful exits. Initial fixture and assertion mistakes are retained separately; none is claimed as an engine defect. In particular, the symbolic-link fixture fails through the existing public reader too, and the test checks that existing error contract.

Both arms use real dagger/dagger `ff0b029a4d270a651b9a8c7286babc79089066e4`, baseline Go module `de633b12ed2aa02e42adb698a23fcecc13faf36d`, engine `3d1c4dee…` and CLI `97f7d82d…`. Schema preparation and callback-caller reuse are enabled in both arms; parallel admission and shared receiver decoding are disabled. Every invocation starts a fresh CLI and makes a real source edit on the same warm engine. Both arms complete adding and removing a test before four measured pairs per workload. Telemetry, normal GC and final flushing remain enabled. These results establish neither a cold-start gain nor a Rust build-time gain.

## Single-pass ownership

The next candidate combines module-relative ignore checks and nested-module ownership into one path walk. It stops when a file is already excluded. The same predicate also handles glob-matched paths outside the literal module prefix, preserving that separate behavior. Public collection getters, ownership policy and test granularity remain unchanged. The worst case remains linear in path depth; this removes a second traversal and temporary records rather than changing that bound.

Fourteen focused checks pass, including a new fixture for independent per-file state, ignored filenames, invalid nested boundaries, and module roots themselves named `testdata` or `_private`. Those names are ignored relative to the module, so their own code must remain discoverable. The new fixture also passes against the original implementation, including the existing glob behavior.

| Complete-command median | Two ownership walks | One ownership walk |
| --- | ---: | ---: |
| Ordinary-source edit | 6.30 s | 5.73 s |
| Test-file edit | 17.13 s | 16.11 s |
| Ordinary-source edit, engine CPU | 26.96 CPU-s | 24.40 CPU-s |
| Test-file edit, engine CPU | 50.59 CPU-s | 50.51 CPU-s |
| Ordinary-source edit, allocated bytes | 5.21 GB | 5.02 GB |
| Test-file edit, allocated bytes | 9.95 GB | 9.82 GB |

The source-edit comparison improves in all four pairs, with a median paired saving of 0.47 seconds. The test-edit comparison improves in three pairs, but CPU-pressure measurements vary substantially: host CPU `some` pressure occupies 24–50% of each measured interval, compared with 19–27% during the source cohort. Test-edit elapsed time ranges from 9.17 to 21.28 seconds while engine CPU is nearly flat between the medians. The candidate remains experimental pending a cleaner test-edit comparison; these observations do not isolate the cause of the slower intervals. All 24 timing commands return correct ordered names and full rows, and exit successfully.

A bounded confirmation attempt waits for quieter CPU conditions before each command. Pressure rises again during initialization: its first three successful commands measure 37–62% host CPU `some` pressure. That attempt is stopped before measured pairs, with every completed command and interruption retained. It establishes no additional performance gain. CPU pressure is an observation, not proof that unrelated host work caused the delays.

The four ownership profiles preserve the original invocation shape exactly: test edits perform **804 evaluations, 1,494 SDK requests, 800 getter executions, 799 test-discovery hits and one discovery execution** in each arm. Ordinary-source edits retain three evaluations, 572 SDK requests and 800 getter/discovery hits. All four streams are lossless, with no dropped events or open operations. No getter body or cache-identity step is bypassed. Variable profile durations are diagnostic observations and are not pooled into the timing cohorts.

Both arms use the same baseline module, real repository, engine, CLI, flags and complete-command protocol as the header experiment. There is no new engine API, library, cache, lock or shared invocation state. Mutable path counters remain local to one file's sequential `any` traversal. This is a Go-library change; cold and Rust performance are unmeasured. Its gains are not additive with earlier cohorts.

An earlier version retained a duplicate legacy predicate for paths outside the module prefix. Its ordinary-source comparison was **6.03 → 5.74 seconds**, faster in three of four pairs. It was refined before selection. A separate timing-harness initialization began before the correctness harness restored its flags; that attempt was interrupted and excluded completely. Its logs, source and restoration are retained with the other attempts.

[Reviewable patches, exact sources, checks, all timing attempts and eight lossless profiles](experiments/go-discovery-path-walks/). The engine binaries and cache volumes are retained; workspace files and diagnostic switches are restored. No PR is opened.
