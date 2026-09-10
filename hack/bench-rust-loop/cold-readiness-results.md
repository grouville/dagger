# Full cold trace and transport readiness experiment, 2026-09-10

This is a CLI transport-readiness change, not a cache or session-lifetime change.
The readiness Info RPC waits for a ready gRPC transport instead of failing fast
and sleeping a whole second. Server-side Unavailable responses still use the
existing retry; cancellation and Unimplemented compatibility are preserved.
Other RPCs retain their existing fail-fast behavior and connection backoff.

## Evidence

Same pinned ripgrep, Rust image, engine image, compiler and CLI build flags as
`first-use-results.md`. Both trials provision a new engine volume and fresh XDG
state. The CLI, engine image, local module, native Rust image and Docker are
already installed. This is NOT a complete installation benchmark. Native means
Cargo through docker exec, not host Cargo. Each timing below is one diagnostic
trial with profiling and local telemetry export enabled, not a distribution.

| Boundary (ms) | Before | Readiness candidate |
| --- | ---: | ---: |
| Engine provisioning through first check | 36926.55 | 43752.93 |
| CLI first check | 36718.59 | 43537.23 |
| Creating client | 2044.59 | 1092.95 |
| Starting session | 402.72 | 451.11 |
| Image resolution | 2162.56 | 2158.16 |
| Image download (pulling) | 11269.97 | 13608.28 |
| Image unpacking | 10742.14 | 10272.59 |
| apt/rsync installation process | 3205.84 | 4880.33 |
| Source reconciliation plus Cargo process | 6200.72 | 10284.80 |

The client boundary improved by 951.65 ms, but the full run regressed by
6826.38 ms amid higher transfer/setup/compilation costs. Do not claim an overall
cold-start win from this pair. Before: two failed Info probes, each followed by
a one-second timer. After: one Info probe waits for transport readiness. The
remaining roughly one second includes gRPC reconnect backoff; it is not all
engine computation. This experiment does not establish long-outage behavior or
cross-platform performance, nor does it eliminate reconnect backoff.

Both complete harness runs passed app/library edits, compile-error detection,
repair and revisiting the earlier failing source. Their disposable engines and
volumes were removed; normal dev-engine state was untouched. Warm timings are
retained in each run's timings.csv, but two samples cannot establish a warm win.

## Profiling quality

Used the maintained wcprof native and OTel analyzers, with the telemetry-capture
skill's otlpdump receiver. Each CLI trace was selected separately from the JSONL
stream. The OTel structural gates both PASS: one root, zero open operations,
missing spans, dropped links, orphaned parents, unresolved waits or cycles;
240/240 declared instrumented spans received. Replay drift is -2.1% before and
-1.8% after. What-if savings are approximate candidates, not measured speedups.

The before native dump has 637 operations, eight roots and zero dropped/open
operations. Its disconnected-root ranking obscures the image bottleneck. The
complete OTel trace correctly ranks HTTP transfer, unpacking, exec processes and
readiness above the millisecond-scale module/query costs. Do not sum nested span
durations or the parallel HTTP layer downloads. OTel covers 36650.70 ms of the
36718.59 ms CLI wall time before; the remaining 67.89 ms is outside the root span.

Local artifacts (not published: traces can contain source paths and diagnostics):

- Before: /tmp/dagger-rust-loop-z25qpi9g and
  /tmp/dagger-rust-cold-first-trace.jsonl.
- After: /tmp/dagger-rust-loop-7006zwfa and
  /tmp/dagger-rust-readiness-first-trace.jsonl.
- Reports: /tmp/dagger-rust-cold-first-otel-analysis.txt and
  /tmp/dagger-rust-readiness-first-otel-analysis.txt.

## Regression coverage

`go test ./internal/buildkit/client -run '^TestWait' -count=3` exercises a
transport that fails then becomes ready (deadline below the old polling delay),
cancellation, success, Unimplemented compatibility, permanent server errors,
and server Unavailable retry until deadline.

## Next bottlenecks

1. Reduce toolchain bytes downloaded and unpacked without assuming users have
   pre-pulled an image. Account for any replacement image/tool provisioning.
2. Remove runtime apt installation through reusable tool packaging, not by
   moving an uncounted install outside the timer.
3. Profile source reconciliation versus Cargo separately. Keep content-aware
   invalidation and the compile-error revisit regression.

The skill-guided boundary tracing motivated a small transport change instead of
bringing back the earlier experimental session retention or custom cache APIs.
