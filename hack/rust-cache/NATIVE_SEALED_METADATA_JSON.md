# Sealed client metadata: contention falls, command latency stays mixed

This experiment remains **unselected**. Caching the JSON encoding of sealed client metadata improves concurrent metadata reads, but does not establish enough complete-command benefit to justify another per-client cache.

The workload is the real dagger/dagger checkout, running `dagger check --module go --check test --list --all`. Timings include a fresh CLI, current-source discovery, 4,398 ordered rows, telemetry, output and successful cleanup on a warm isolated development engine. Both modes complete adding and removing a test before four alternating measured pairs per workload.

| Complete listing after an edit | Before | Candidate | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 8.75 s | 8.49 s | 3/4 |
| Ordinary-source edit | 5.44 s | 5.35 s | 3/4 |

The test-edit paired differences range from a 1.03-second regression to a 1.15-second saving. Engine CPU changes 41.10 → 40.58 CPU-s for test edits and 22.07 → 22.24 CPU-s for ordinary edits. Allocation falls by only 23.2 MB and 3.3 MB respectively. These results do not demonstrate a substantial latency improvement. They are separate cohorts from previous experiments and their differences must not be added together.

## Why try it

A lossless wcprof capture showed a shared `Workspace.glob` caller completing well after its shared operation and cache wait ended. A separate mutex profile found heavy waiting attributed to `clientMetadataSnapshot`, which serializes and decodes metadata while holding the session scope lock. That identified a real source of contention; it did not prove that metadata copying explains the whole glob delay.

Client metadata is immutable after sealing. The candidate checks sealing under the existing lock, captures the immutable pointer, then releases the lock. A per-record `sync.Once` retains its JSON encoding. Every caller still decodes its own independent snapshot, including the internal recipe-ID setting. Bootstrap validation, permission checks and client ownership remain in place.

The standalone source adds three record fields and factors out the existing JSON decoder. Its concurrent test compares snapshots against the original clone operation, mutates nested maps and slices returned to 64 readers, and verifies that subsequent reads remain independent.

## What the profiles establish

Paired lock diagnostics reduce aggregate mutex waiting from approximately **121 to 72 seconds summed across goroutines**. The corresponding instrumented complete commands take **5.70 → 6.15 seconds**. Aggregate waiting overlaps across goroutines and cannot be presented as elapsed time saved. Lock sampling and CPU/wcprof capture make these diagnostics distinct from the unprofiled timing cohort.

The component benchmark improves concurrent reads from 8.47 → 1.18 µs with no labels and 53.32 → 8.23 µs with 32 labels. Serial reads improve less. A fresh record's first read is slightly slower and allocates one more object in this fixture. These component results do not establish cold-engine performance.

Each candidate profile encodes only two metadata records, totaling **2,226 bytes**. Avoiding repeated encoding removes little total allocation. The CPU profile still points to interpreted list reductions and binary operators as a larger investigation target. A smaller lock-scope change may be preferable; this experiment does not compare those alternatives.

## Full pipeline checks

All 24 timing commands return correct ordered rows and exit successfully. Test-edited profiles retain **all 800 collection getter executions and 799 unchanged test-discovery hits**. Ordinary-source profiles retain getter and test-discovery hits. No stored-item substitution or getter suppression is used.

Eighteen Go commands and 28 Rust/native-cache cases pass with their expected outcomes. They cover discovery changes, ownership and settings, selected test execution, expected test failures, invalid unselected neighboring packages, repaired workspaces, binaries, generation, source-version restoration and native compilation-action hits. The exact engine overlay's full server race suite and the standalone snapshot mutation checks pass. This is behavior evidence, not a Rust latency measurement.

The archive retains an initial test failure caused by omitting a flag required by an existing diagnostic test, followed by the corrected successful suite. It also retains a capture rejected before CLI launch by the unchanged host-pressure admission check, and the later successful capture. Six final captures are lossless. All eight engines and their volumes are retained; profiling and experimental flags are restored.

## Sources and limits

[Evidence](experiments/sealed-metadata-json-engine/) includes the standalone patch and test, exact engine overlay changes, source manifests, component measurements, all attempts, complete-command samples and raw profiles. The parent engine source archive is referenced by hash. The candidate binary is `e5d9d9c9957bc9989cae8d0fbf9bbbfd559ace982be823431236486aace06cf6`; the Go module is `de633b12ed2aa02e42adb698a23fcecc13faf36d`.

No PR is prepared for this candidate. Current cold listing, retained-cache restarts and Rust latency remain unmeasured. The next experiment should remove work in the normal discovery path and retain the same discovery, getter, selection, execution and cleanup checks.
