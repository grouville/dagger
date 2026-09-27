# Span-runtime trial: foreground shutdown attribution

Read-only capture of the existing **44 completed commands** from all three stopped, owned `collections-span-runtime-v1` engines. Immutable container IDs and ownership labels were verified against the trial's `engines.json`; raw Docker logs remain private. No build, restart, CLI workload or Cloud request was added. All 44 commands have one main-client record for each of the five expected shutdown phases.

The generation fixture is a native Dang `@generate` function copying input contents to a generated output. It is **not SDK code generation**. Both ordinary engines include the same metric fix and experimental SDK stack; the differing candidate is the span routing/serialization change. The original experiment's provenance and correctness remain authoritative.

## Warm generation: the regression is not local telemetry flushing

| Pair | CLI baseline → candidate | Cloud flush baseline → candidate | Output visible baseline → candidate | GC counts baseline / candidate |
| --- | ---: | ---: | ---: | ---: |
| 0 | 717.7 → 926.4 ms | 281.7 → 416.0 ms | 311.1 → 364.5 ms | 1 / 1 |
| 1 | 739.5 → 817.5 ms | 300.9 → 355.6 ms | 312.7 → 309.8 ms | 0 / 0 |
| 2 | 728.6 → 824.2 ms | 309.1 → 349.9 ms | 294.2 → 336.4 ms | 0 / 1 |

The candidate is slower in all three CLI pairs. The measured foreground **Cloud-flush phase is also longer in all three**, by 134.4 / 54.7 / 40.8 ms. Local session telemetry flush is only 0.10–0.52 ms; workspace locks and service stop are microseconds. There is no tens-of-milliseconds regression in that local flush phase.

The no-GC pair is especially useful: +77.9 ms CLI includes +54.7 ms Cloud flush, with output observed 2.9 ms earlier. The difference outside the entire recorded shutdown handler is +23.1 ms, which still includes CLI transport/provider cleanup and other phases; it is **not** a measured engine computation regression. Output polling is every 5 ms, so that small visibility difference is within its sampling granularity.

For pairs 0 and 2, output appears +53.4 / +42.2 ms later. Their candidate CPU readings and GC counts warrant further isolation, but do not establish GC as the cause. Stop-the-world pause deltas are only 0.058 / 0.059 ms for those candidate runs, not tens of milliseconds. Concurrent GC/assist can cost CPU, and the pre/post counter brackets include background work, so pause duration alone neither explains nor excludes a GC effect.

The Cloud phase combines pending trace/log exports and the refresh-file gate. It does **not** identify request count, queue wait, network RTT, server processing or why their timing changed. The routing patch changes local storage, but producer timing can indirectly change export batching. These phase logs localize the observed wait; they do not prove the patch caused a Cloud-network regression or that the result can be dismissed as noise.

## Other measured flows

Medians are descriptive; comparing medians does not substitute for the paired rows in `summary.json`.

| Flow | Pairs | CLI baseline → candidate | Cloud flush baseline → candidate | Local flush baseline → candidate |
| --- | ---: | ---: | ---: | ---: |
| `list -a` | 5 | 2279.7 → 2128.5 ms | 500.8 → 415.5 ms | 2.40 → 1.47 ms |
| `ws ls` | 3 | 562.5 → 560.3 ms | 155.9 → 152.3 ms | 0.27 → 0.42 ms |
| Warm native generation | 3 | 728.6 → 824.2 ms | 300.9 → 355.6 ms | 0.11 → 0.21 ms |
| Edited native generation | 3 | 931.1 → 923.4 ms | 382.0 → 384.7 ms | 0.24 → 0.18 ms |
| Selected unit check | 2 | 2407.2 → 2231.9 ms | 342.4 → 362.1 ms | 1.53 → 1.71 ms |

The selected-check median improves despite a slightly larger foreground Cloud-flush median, so shutdown is not the sole source of whole-command variation. Conversely, artifact pair 1 is +1165.9 ms slower on the candidate while its Cloud-flush difference is only +14.3 ms. These ordinary invocations have no detailed paired query profile, so this audit does not invent a source for that larger pre/post-handler difference.

Final session shutdown is distinct from the foreground `/shutdown` handler. Of 15 recorded final telemetry-shutdown summaries, 14 finish after CLI exit; one edited-generation summary finishes 76.2 ms before exit while CLI cleanup can still run. Its mere completion before CLI exit does not establish that the CLI awaited it. Do not add those background durations to foreground phase totals.

## Decision supported by this evidence

Keep the span candidate isolated until the warm-generation difference is understood. Local-flush timings alone do not substantiate a regression in serialization itself, but the three consistently slower complete commands cannot support a no-regression claim either. A discriminating next comparison is paired native-generation query/output timing with local telemetry only, followed by separate Cloud diagnostics that count actual exports and split queue/response time. Counter brackets and engine history must remain matched; forcing GC before commands would change the normal-user boundary and cannot replace the primary trial.

`numeric-phases.json` exports allowlisted labels, relative timing, command ordinals and booleans only. `summary.json` adds existing numeric CLI/file-visibility/CPU/GC values and paired deltas. Raw logs, session/client IDs and trace content are excluded from the publication allowlist.
