# Filtered-listing engine allocation diagnosis

The same warm filtered listing allocates roughly **574 MB per command** in the unprofiled identical-binary control. The new engine profile identifies repeated module/schema materialization and substantial garbage-collector CPU. This is an actionable allocation problem; it does not establish that the earlier CLI formatter or sparse-export patches caused the noisy filtered-listing timing difference.

The preceding identical-binary control had a −18 ms median paired difference, with individual pairs spanning −252 to +293 ms. See `../filtered-identical-memstats-v1/analysis.md`. Both labels were the same production executable.

## Measurement and validation

This separate diagnostic reuses the frozen static-TypeScript engine, production CLI, restored Kyle greetings fixture and audited local-only environment. Eight ordinary filtered-listing commands all exited successfully with identical expected bytes. Source hashes stayed unchanged. No GC was forced; no engine settings, API semantics or caching policy changed.

The five-second idle CPU profile contains zero CPU samples. The active CPU profile lasts 35.004 seconds and its embedded timestamps cover every command: the first starts 0.256 seconds into the profile and the last exits at 17.843 seconds. Thus the profile includes commands, their asynchronous cleanup and a subsequent idle interval. These profiled command timings are excluded from baseline/candidate performance comparisons.

Process-wide `TotalAlloc` increased by 4.872 GB through the command block and 4.964 GB by the final profile bracket. The sum of the eight per-command brackets is 4.830 GB. Those totals include profiling/background activity; they do not exclusively measure query execution. The surrounding idle-profile/snapshot bracket itself allocated 71.6 MB and consumed 0.49 cgroup CPU-seconds, while the actual five-second idle CPU capture had zero samples. Snapshot construction is visible overhead.

The engine process CPU profile contains 28.54 sampled CPU-seconds. The container cgroup records 34.22 CPU-seconds over the wider bracket; that counter also includes container child processes and profile collection boundaries, so these are different measurements.

## CPU attribution

| Cumulative stack | CPU seconds | Sample share |
| --- | ---: | ---: |
| GC background mark worker / drain | 9.42 | 33.0% |
| Module source definition through SDK | 5.06 | 17.7% |
| Dang ModuleTypes | 3.13 | 11.0% |
| Dang cached-syntax clone | 1.40 | 4.9% |

Rows overlap where one function calls another. GC includes 6.43 seconds on idle-worker paths and 2.99 seconds on dedicated-worker paths. This proves concurrent collector work exists; it does **not** mean 33% of CLI wall time is removable. The profile includes a cleanup tail, and idle-worker CPU need not block a command. Small stop-the-world pauses alone would miss this cost.

## Allocation attribution

The sampled allocation delta is 1,386.58 MiB immediately after the commands and 3,025.36 MiB after the CPU profile ends. Go documents that memory profiles can be up to two GC cycles old; the engine completes two collections by command-block end and three by final capture. The changing sample totals demonstrate why these samples must not be divided by eight and presented as exact per-command allocation savings.

The later sample is useful for identifying callers:

| Stack | Sampled cumulative MiB | Interpretation |
| --- | ---: | --- |
| Module source definition through SDK | 1,017.31 | Broad module-load subtree, includes several rows below |
| Dang evaluation | 627.56 | Rebuild/evaluate module environment |
| Dang ModuleTypes | 542.33 | Type metadata work |
| Static TypeScript prototype types | 323.32 | Prototype still materializes metadata |
| DagQL preselect | 307.55 | Request preparation around execution/cache lookup |
| Local span export | 283.02 | Local telemetry storage also matters without Cloud |
| Cached Dang syntax clone | 221.12 | All attributed to ParseFileCached; 96 MiB through reflect.New |
| Server.Fork | 106.28 | Schema isolation/copying |

These cumulative values overlap and include sampling error/publication lag. They are leads, not an additive budget.

Two particularly specific caller breakdowns:

- `Interface.FieldSpecs` allocates 94.54 MiB directly; **84.53 MiB (89.4%) comes from `Interface.Satisfies`**. The existing interface reconciliation repeatedly enumerates fields. A pass-local immutable snapshot can reduce allocations while preserving view/version rules and mutations between passes. The SDK audit agent is investigating this path.
- `InputSpecs.Inputs` allocates 77.04 MiB directly: 26.02 MiB under argument definitions, 18.51 under preselect, 18.50 under argument compatibility, and 13.51 under sorting arguments. Avoid treating all of this as TypeDef clone execution; saved wcprof shows many metadata cache hits and few executed TypeDef clone bodies.

Local span export also deserves a separate narrow experiment: 72.51 MiB is below `MarshalProtoJSONs`, 62.01 MiB below direct protojson marshaling, 71.96 MiB below DB.Open, and 32.45 MiB below AppendSpans. These are measured call-stack costs, not proof of a store-lifetime bug. Reusing immutable prepared rows across fan-out or avoiding repeated JSON assembly may help, but must preserve routing, ordering, durable storage and all span fields. Count real fan-out/reopens before proposing lifetime changes.

A cache-prune/usage-sampling subtree is also present in the earlier allocation delta (124.46 MiB cumulative). That work depends on the long-lived cache population and is process background work, not necessarily repeated per listing. Any reduction must retain ownership holds and accurate physical-size accounting.

## Next action

Prioritize eliminating repeated field/schema/syntax materialization while retaining session/view/content identity. Then remeasure engine allocations and unprofiled command latency. Do not tune GC, weaken telemetry, add a cross-session TTL, or claim the entire measured GC CPU as an available latency reduction.

Raw CPU/allocation profiles remain private under `private/`. Only numeric verification and function-level aggregates are suitable for the shared report. No raw expvar, credentials, telemetry payloads or profile labels are retained in the shareable allowlist.
