# CLI telemetry close experiment: validation and build handoff

The isolated queue-worker backport and joined early log flush pass their focused tests, including race detection. Three ordinary CLIs were built from the same clean Dagger commit, `85b60f7a0a16a27459ef571bc94bcf870c876dcc`. No engine or Cloud workload was run during this validation.

## What is being compared

| Variant | Change relative to current CLI |
| --- | --- |
| baseline | None; unchanged log SDK v0.16 and sequential provider close |
| queuefix | Backported single-worker queue and chunk-drain behavior only |
| overlap | Queuefix plus early `logs.ForceFlush`, joined before log-provider shutdown |

All variants share the same source commit, compiler flags, module versions, unmodified local copies of the pinned dependencies, and committed metadata optimization. Only the documented Go overlay source files differ. The engine remains the existing `9912b763…` binary. Source hashes, compiler hashes, exact commands, binary hashes and build results are recorded in `builds/build-recipe.json`, `builds/manifest.json` and `builds/build-results.json`.

The overlap variant starts a bounded flush of records already queued while trace shutdown proceeds. It joins that flush, then shuts down logs and metrics in their original order. Logs emitted by trace cleanup or error reporting still reach the open logger. This is not detached export: CLI exit still waits for provider cleanup.

## Validation

| Test gate | Result |
| --- | --- |
| Worker backport, six initial common lifecycle cases | Pass |
| Sequential close, overlap witness | Expected failure: pending logs cannot export while trace shutdown is held |
| Overlap, nine initial lifecycle cases | Pass |
| Overlap, eleven cases including added worker semantics | Pass |
| Worker-only applicable cases, race detector | 8/8 pass |
| Overlap cases, race detector | 11/11 pass |

The tests cover actual SDK batch processors and local fake exporters: output order; late trace-cleanup/error records; joining a blocked log export; no empty upload; synchronous and scheduled export errors; cancellation; no trace provider; draining 1,615 records across batches; canceled flush retaining queued records; and attempting later chunks after an earlier forced-drain export error. Export calls remain serialized per exporter. These tests establish these bounded contracts, not universal delivery under process death or an exhausted shutdown deadline.

## Why this is a backport experiment

The first released log SDK containing the upstream worker correction is v0.21 (OTel v1.45), which also removes the old `log.Value`/`log.KeyValue` API. A direct upgrade failed during compilation, before tests ran. The local compatibility audit found 25 production Go files and the pinned `dagger/otel-go` dependency using that older API. v0.20 still uses the old worker. A broad API migration would confound this performance experiment.

The prototype therefore keeps the v0.16 public API and LoggerProvider, takes the v0.21 batch worker with unrelated experimental observability removed, and replaces only `chunkExporter.Export` in the old exporter helpers. The original Apache-2.0 notices and license are retained. Exact adaptations and source hashes are in `manifest.json`; `worker-backport.patch` is reproducible source evidence. The copied module is necessary because Go disallows file overlays underneath GOMODCACHE.

This is not a recommendation to maintain a vendored SDK fork. If performance justifies it, the shipping path is a coordinated dependency/API update or a maintained upstream-compatible release. The small joined-close change belongs in `dagger/otel-go` and needs its own review even if the worker update is adopted separately.

## Remaining measurement

Compare the three builds against the same local real ingestion API without injected latency, then attribute queuefix separately from queuefix plus overlap. HTTP acknowledgement and a quiet receiver interval are not a complete record-delivery proof. The local API timings also do not predict production network savings. No performance improvement is claimed by this validation alone.

Upstream references: [worker fix #8620](https://github.com/open-telemetry/opentelemetry-go/pull/8620), [v1.45 release](https://github.com/open-telemetry/opentelemetry-go/releases/tag/v1.45.0), [v0.20 batch implementation](https://raw.githubusercontent.com/open-telemetry/opentelemetry-go/sdk/log/v0.20.0/sdk/log/batch.go).
