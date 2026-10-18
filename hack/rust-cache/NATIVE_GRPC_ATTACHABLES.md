# Native gRPC reduces CLI CPU; listing latency is not confirmed

The opposite-order confirmation does **not** reproduce the listing gain: **34.04 → 34.16 seconds median**, faster in only **4/8 pairs**. CLI CPU decreases **25.91 → 20.17 CPU-seconds**, lower in every confirmation pair and all **12 total pairs**. The candidate remains unselected for the end-to-end latency goal. No standalone proposal or PR is added.

The earlier four-pair screen gives **34.15 → 31.29 seconds**, with a compaction-overlapped control and one 64 ms difference. It remains below as historical evidence, not a confirmed improvement. Every command in both cohorts returns the correct ordered rows and exits successfully through cleanup.

## Change and motivation

The existing runtime trace locates substantial host-callback scheduling work in `http2.Server.ServeConn` and `grpc.Server.ServeHTTP`. That route passes each gRPC request through Go's separate HTTP/2 server implementation, including its response-flush and stream-close machinery.

The candidate uses **`grpc.Server.Serve` over the same upgraded connection**. A small listener adapter gives that connection the same session lifetime. A connection-context adapter preserves the `Run` context, including its values and deadline, together with gRPC's peer and request metadata. The concurrent-stream limit remains **250**, matching the existing HTTP/2 default.

This changes the CLI's generic host-callback transport, not the Go module, compiler cache or collection granularity. Every filesystem read remains fresh. Telemetry remains enabled. There is no new dependency, host-file cache, callback suppression, deferred cleanup or engine replacement.

## Complete repository command

Command: `dagger check --module go --check test --list --all` on dagger/dagger `ff0b029a`, with Go module `7568cd0`, Go 1.26.6 and controlled engine `4080ad95`. CLI control is `e7ba08d0`; candidate is `99afa842`.

The engine and compiler caches are warm. Every invocation starts a fresh CLI and receives a fresh source-comment edit. Both arms enable native telemetry storage and the same selected engine optimizations. Ordinary GC, snapshot collection, telemetry and final cleanup remain enabled; profiling is off during timing. An explicit final engine-log flush is included. A local telemetry receiver does not model production Cloud latency. No cold-start or edited-Rust speedup is established.

| Measured pair | Existing transport | Native gRPC |
| --- | ---: | ---: |
| 1, control first | 46.58 s | 30.76 s |
| 2, candidate first | 34.01 s | 31.82 s |
| 3, control first | 32.08 s | 32.02 s |
| 4, candidate first | 34.30 s | 29.23 s |
| Median | **34.15 s** | **31.29 s** |

All eight measured commands return **4,398 identical ordered rows**. Initialization adds a real test and correctly returns **4,399 rows** in both arms: **32.91 seconds candidate, then 32.17 seconds control**. That pair is excluded as planned, despite favoring the control. Every one of the ten commands succeeds. No observation is discarded or repeated to improve its number.

The first control's class slots fall **1,072,980 → 608,894**, so its entire 15.82-second gap cannot be assigned to transport. Every other measured run grows by approximately 24,018 slots, with no recorded reduction. Host I/O pressure is approximately **0.08–0.16%** across measured commands. Ordinary maintenance remains enabled. The 64 ms third-pair gain is too small to establish an individual improvement.

Engine allocation changes **25.27 → 24.97 GB per command** and engine CPU **150.68 → 143.71 CPU-seconds** at the column medians. Allocation is cumulative, not resident memory; CPU totals are not elapsed savings. The four paired savings have a **3.62-second median**, separate from the **2.86-second difference between column medians**. The first comparison is not sufficient to claim a general speedup over stock main.

## Component and diagnostic evidence

Four alternating fresh-process pairs run real stat/read callbacks over loopback TCP, reading a 1,649-byte file. Both implementations use the same stream limit, messages and filesystem operations, with ordinary GC and `GOMAXPROCS=8`.

| Stat plus read | Existing transport | Native gRPC |
| --- | ---: | ---: |
| 8 workers, ns/op | 131,976 | 72,603 |
| 128 workers, ns/op | 117,109 | 44,300 |
| 8 workers, allocations/op | 586 | 481 |
| 128 workers, allocations/op | 579 | 478 |

Each pair improves at both sizes. Parallel ns/op measures inverse throughput, not the latency of an individual request. This component result does not establish a corresponding full-command gain.

A separate candidate CLI capture succeeds with the exact rows in **36.06 seconds with profiling enabled**. It is excluded from timing. Its CPU samples positively identify the native gRPC HTTP/2 server and contain no `grpc.Server.ServeHTTP` or x/net HTTP/2 server frame. The earlier selected-CLI capture contains those adapter frames.

The independent diagnostic profiles sample **24.90 → 18.89 CPU-seconds**. Aggregate runnable scheduling delay is **28.07 → 5.53 seconds across goroutines**. These are different diagnostic runs; concurrent delays cannot be presented as elapsed time saved. The new capture retains other blocking, including more cumulative blocking under the filesync handler, so the profiles do not prove that every request phase improves. They verify the changed execution path and motivate confirmation.

## Opposite-order confirmation and decision

The identical binaries, engine, source, Go module, cache volume and common flags run eight fixed alternating pairs with the starting order reversed. Telemetry, ordinary maintenance and cleanup remain enabled; profiling is off. Both arms keep native telemetry storage enabled. There is no reset, forced collection, discarded observation or implementation change.

| Measured pair | Existing transport | Native gRPC |
| --- | ---: | ---: |
| 1, candidate first | 34.65 s | 35.14 s |
| 2, control first | 33.60 s | 29.46 s |
| 3, candidate first | 45.36 s | 44.67 s |
| 4, control first | 49.63 s | 36.06 s |
| 5, candidate first | 32.65 s | 63.46 s |
| 6, control first | 32.85 s | 33.19 s |
| 7, candidate first | 34.47 s | 29.06 s |
| 8, control first | 30.80 s | 31.61 s |
| Median | **34.04 s** | **34.16 s** |

All sixteen measured commands return the same ordered **4,398 rows**. The excluded initialization pair adds a real test and returns **4,399 rows**, taking **34.93 seconds control, then 48.35 seconds candidate**. All eighteen commands succeed. Across both cohorts, all **28 commands**, including four initialization commands, succeed.

Confirmation engine-CPU medians are **152.41 → 157.77 CPU-seconds** and allocation medians **25.17 → 25.09 GB**. The lower CLI CPU does not establish lower total engine work or elapsed time. The initial favorable cohort is not pooled with the failed confirmation to claim a confirmed latency improvement.

Several long commands coincide with shrinking cache classes and estimates near **4 GiB**. The 63.46-second candidate run starts at **3.991 GiB estimated metadata**, with **756,320 results and 698,102 class slots**, and ends at **3.203 GiB**, with **572,194 results and 523,780 slots**. It also sees about **5.18% host I/O pressure**; the following 32.65-second control sees **7.37%**. These observations remain included and do not isolate transport or maintenance cost.

The snapshot-GC intervals recorded during that long command total roughly **3.23 seconds**, with roughly **0.74 seconds** in their metadata portions. They do not explain the whole elapsed gap. Cache-metadata pruning and class compaction are separate work that needs its own CPU, lock and wcprof attribution. A bounded engine-log read finds no matching prune lines and does not prove those events were absent.

The decision is **CPU reduction confirmed; command speedup unconfirmed; candidate off**. The next experiment targets the maintenance path, with the existing CLI selected and collection semantics unchanged.

## Correctness, risk and next gate

Both implementations pass the same focused race checks for session lifetime, shutdown, initialization failure and the new transport cases. Coverage checks root context and deadline, peer and request metadata, natural peer disconnection, cancellation of one stream while others remain usable, fresh file edits, NotFound status, size-limit errors and a 1 MiB response. Removing the context adapter fails its regression with `lost root context`.

Review strengthens the deadline fixture: its initial request timeout was shorter than the session deadline and could mask lost deadline propagation. The final fixture uses a distinct constructor context, a longer request timeout and the exact expected session deadline. It is checked against both transports and independent missing-value and missing-deadline controls. The original fixture is retained; production code and the timed CLI binary do not change.

The post-confirmation lifecycle audit also passes under the race detector on both transports: canceling `Run` ends an active callback and returns promptly when a peer stalls before sending its HTTP/2 preface. Removing the owned connection close makes the stalled-handshake regression fail. This explains why the adapter closes its one owned connection when it stops. This path uses immediate `Stop`; `GracefulStop` is unused and unsupported by the existing HTTP adapter, so it is not introduced as a new feature requirement.

All **35 selected Go-module checks pass** with the candidate CLI. All six retained native Rust histories reuse every compiler action after the first cohort/capture and again after confirmation: **130/130, 1,026/1,026 and 6/6**, twice at each checkpoint. These are correctness checks, not a Rust timing comparison.

The transport changes its connection and flow-control implementation, so broader platform and service coverage remain part of review. The prototype's initial generated overlay omits a struct field and fails compilation; that failure and its source are retained. The corrected candidate passes before any full-repository timing begins.

Sources, configurations and feature flags are restored after both cohorts, the capture and cache checks. The owned engine is unchanged; the selected CLI remains the original one. Native telemetry writing is off at confirmation finalization, with dual-format readers and v2 support retained. No standalone upstream proposal or PR is prepared from this experiment.

[Evidence](experiments/native-grpc-attachables/) retains exact overlays and source context, all test and component outcomes, every full-command observation and maintenance counter, the expected context-regression failure and initial build failure, retained Rust histories, CPU profiles and a verified compressed runtime trace. The large original control trace remains in the earlier CLI-profile archive. No binary or cache volume is included.

[Confirmation evidence](experiments/native-grpc-attachables-confirmation/) retains the opposite-order cohort, combined assessment and failed latency decision, supported-shutdown regressions and expected failure, post-confirmation Rust histories and final restoration state. The first archive's pending-confirmation decision is historical.
