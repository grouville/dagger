# CLI CPU attribution after metadata optimization

All 11 local-only diagnostic commands passed their exact-output checks. The original engine binary and fixtures were restored and the task engine stopped. The seven CPU captures use the same ordinary CLI `748700a2…`, engine `9912b763…`, and committed metadata optimization. CPU/runtime tracing is instrumentation: these wall times are not another ordinary performance comparison. Raw profiles and command output remain private.

| Capture | Sampled Dagger CPU | Waited process-tree CPU | Instrumented CLI wall |
| --- | ---: | ---: | ---: |
| Core 1 | 40 ms | 193 ms | 264 ms |
| Core 2 | 30 ms | 197 ms | 264 ms |
| Core 3 | 30 ms | 194 ms | 264 ms |
| Module 1 | 80 ms | 247 ms | 414 ms |
| Module 2 | 60 ms | 239 ms | 364 ms |
| Expanded checks 1 | 430 ms | 676 ms | 1,619 ms |
| Expanded checks 2 | 410 ms | 584 ms | 1,769 ms |

The small calls contain only three to eight 10 ms CPU samples. Their individual function percentages are coarse. The larger listing gives a stronger lead: source enumeration and local telemetry processing consume material CLI CPU even with Cloud disabled.

| Cumulative CPU anchor (overlapping, do not add) | Checks 1 | Checks 2 |
| --- | ---: | ---: |
| Filesync sender walk | 170 ms | 100 ms |
| `os.ReadDir` | 80 ms | 60 ms |
| Telemetry consume/decode callback | 30 ms | 60 ms |
| Frontend dispatch | 30 ms | 50 ms |
| GC background workers | 80 ms | 60 ms |

The first listing also samples `filepath.Rel` at 20 ms. The second samples matching/path cleaning at 10 ms each. These are leads inside enumeration, not additive predicted gains. The CPU stacks originate in filesync sender goroutines, so they cannot distinguish parent-directory imports from actual subtree imports. A path-class counter or separate import annotation is required before attributing them all to one source operation.

## Xattrs and stat are not the large cost here

Trace-derived syscall delays show:

| Syscall family, aggregate duration | Checks 1 | Checks 2 |
| --- | ---: | ---: |
| Directory enumeration (`Getdents`) | 37.29 ms | 32.57 ms |
| `Lstat` | 1.79 ms | 1.31 ms |
| `Llistxattr` | 0.60 ms | 0.49 ms |

The import normalization discards UID/GID/xattrs, so an explicit xattr-free import mode is reasonable independently, but these measurements do not make it the next large win. Current fsutil already delays `mkstat`/xattrs until `DirEntry.Info`, after include/exclude filtering. Skipped entries do not all incur those reads. UID/GID share the same stat data needed for mode, size, modification time and hardlink identity; dropping the entire stat would change correctness.

## Fixed connection work and the accounting gap

Four saved execution traces attribute 14.95–17.35 ms of syscall waiting to `containerRuntimeAvailable`, whose Docker implementation runs `docker version`. This is observed subprocess wait, not Docker CPU or the complete availability phase. The core/module traces also contain approximately 37–42 ms of accumulated synchronization delay under `newBuildkitClient`, awaiting the initial engine connection/Info. These waits and cumulative ancestors overlap; they must not be summed as independent removable latency.

Go pprof samples only Dagger, beginning in PersistentPreRunE after initialization/argument parsing. Process-tree CPU also includes waited Docker children. The recorded tree-CPU minus sampled-CPU differences are 153–179 ms for core/module and 174–246 ms for listing. They are not attributable to Docker alone: unprofiled Dagger startup/finalization and sampling error also contribute. The outer wall time minus the rounded pprof duration is 56–101 ms, which bounds the combined before/after-profile wall envelope, not startup CPU. The driver lacks aligned internal self/child CPU snapshots, so it cannot partition this further.

Runtime trace synchronization profiles sum overlapping goroutines: the listing's aggregate waits exceed 40 seconds during a roughly 1.6-second process. That is expected and not a stall duration. The CPU-profiler reader itself appears waiting for most of the capture; that is diagnostic machinery, not application work. No Cloud export cost can be inferred from this local-only run.

## Connection source review

The normal non-nested CLI opens control gRPC, reverse attachables, telemetry HTTP/2 and API HTTP/2 connections. Three proactive tunnels after the initial answered tunnel therefore match three real later consumers for these flows; they are not proven unused speculation. Turning prewarming off would usually serialize already required startup.

Sharing the API and telemetry HTTP/2 transport could remove one physical connection, but must preserve request cancellation separately from transport ownership. The current API transport closes its physical connection on the client-close signal, while telemetry deliberately survives that signal until its final drain. A shared pointer alone is not correct. The separate reverse attachables and BuildKit connections remain necessary under the current protocols. A source-only design/test review will cover a shared transport and an accompanying reduction from three to two proactive dials; neither is implemented or timed here.

`numeric-cli-evidence.json` retains per-capture sampled totals, nonadditive function anchors, top flat/cumulative function tables, trace delay anchors and binary/profile hashes. `analyze_cli.py` derives it from saved profiles without launching workloads. The engine wcprof is analyzed separately.
