# Skip Cloud metric requests containing no metrics

## Context and change

The metric SDK's PeriodicReader performs a final collection at shutdown even
when the CLI recorded no metrics. A diagnostic build measured three empty Cloud
metric Export calls at 76.5, 79.7 and 86.7 ms. These were real requests in the
configured-account path, not Cargo execution or a cache miss.

Skip only non-nil ResourceMetrics with zero ScopeMetrics, before consuming a
Cloud sequence number. Preserve cancellation and post-shutdown errors. Nonempty
collections, explicitly present empty scopes, nil inputs, exporter errors,
ForceFlush and Shutdown still use the existing exporter. No telemetry opt-out,
timeout, buffer, sampling, retry or authentication changes are involved. The
optimization has no expected benefit when Cloud exporting is not configured.

This is a narrow platform change, not a Rust-specific execution cache.

## Correctness

Go 1.26.8, fixed source and dependencies, focused command:

```sh
go test -buildvcs=false ./engine/telemetry \
  -run 'Test(SequencedMetrics|ExportSequenc)' -count=10 -timeout=60s
```

PASS, package 0.010 s. The existing HTTP retry/sequence tests require permission
to bind a loopback port; the first sandbox attempt failed for that environmental
reason and is retained. New tests exercise cancellation, sequence continuity,
shutdown state, nil/explicit-scope forwarding, errors and exporter delegation.
A real SDK PeriodicReader's final empty collection is suppressed; recording a
counter instead delivers exactly one collection containing value 7.

Negative control: replace only cloud_export_sequence.go with the unchanged
baseline and run TestSequencedMetricsFinalSDKCollection/empty. It fails at the
intended assertion: the underlying exporter receives one empty collection.

## End-to-end experiment

Current-main stack base: db9d005c715ac9d146780d783faf7f7b55d23e5e,
rebased onto upstream 6bf59d50654ce9244ebeee1cc090b7dce3fe3083.
Both CLIs built from the same source directory with Go 1.26.8, CGO_ENABLED=0,
identical -buildvcs=false/-s/-w/RunnerHost flags; only the control uses an overlay
restoring the unchanged production file. No diagnostic instrumentation in either.

- Control CLI SHA256: 98879f673c068137e9621726bd1d4cd5b2ae708e7592e0fc50bc77e64a530f3a
- Candidate CLI SHA256: fa588227a42f336ca32483b48e8c17e01906a7899b4b5197b6f8651536fe6c88
- Same engine image: sha256:3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181
- Maintained wcprof analyzer SHA256: de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba

Ordinary standalone `dagger check rust:check`, unchanged pinned ripgrep fixture,
same workspace/module/engine/account/cache histories. Ten alternating pairs,
with one declared per-binary warmup pair excluded. Account and default analytics
settings inherited on both sides; no DO_NOT_TRACK/DNT override. Local complete
live OTel capture enabled identically. This is an instrumented CLI A/B, not a
native-Cargo, first-installation, or unconfigured-account comparison.

| Metric (ms) | Control median | Candidate median | Paired median saving |
| --- | ---: | ---: | ---: |
| Complete CLI process | 1064.321 | 999.272 | 62.365 |
| Before CLI root | 56.305 | 61.843 | -5.264 |
| CLI root | 501.413 | 515.249 | -12.386 |
| After CLI root | 506.949 | 427.188 | 64.141 |

Candidate faster in 8/10 process pairs; all regressions retained. Paired process
savings, ms: 8.282, -14.419, -43.448, 80.410, 148.553, 136.928, 90.831,
185.011, 25.385, 44.319. Control range 983.342–1122.810 ms; candidate
922.635–1042.400 ms. These ten pairs do not establish a precise universal saving.
Do not add medians of different phases or substitute differences of marginal
medians for paired statistics.

All 22 complete wcprof traces pass structural/completeness/replay gates. Each
contains the same three cached Container.withExec operations and zero actual
exec.processRun operations. Source hashes and engine identity/restart state
are unchanged. Complete traces and top-60/chain reports were analyzed, not just
the CLI root duration. The root performance variation is retained; the measured
saving is in the shutdown region outside that root, consistent with the prior
exporter-boundary diagnosis.

## Reproduction and retained evidence

The local evidence package `/tmp/dagger-empty-metric-export.n6NHX6VB` contains
build.sh, the control overlay, the focused test/negative-control logs, pinned
run-ab.py and analyze-ab.py, and build/runtime/analysis logs. Run:

```sh
bash /tmp/dagger-empty-metric-export.n6NHX6VB/build.sh
python3 /tmp/dagger-empty-metric-export.n6NHX6VB/run-ab.py
python3 /tmp/dagger-empty-metric-export.n6NHX6VB/analyze-ab.py RUN_DIRECTORY
```

These scripts deliberately require the frozen local engines, binaries and
workspace; they are not a portable user demo. Preserve the existing account on
both sides and use a running complete OTel receiver. The measured run is
`/tmp/dagger-empty-metrics-ab-48_c8kdb`: processes.jsonl, metadata.json,
summary.json and analysis/report.json retain every timing and trace gate.
The private analyzer executable/source is not included in the repository.

The broader Rust goal is still unmet. This does not solve first-use toolchain
delivery, unchanged CLI latency, edit invalidation overhead, or artifact export.
