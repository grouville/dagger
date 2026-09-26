# Filtered-listing follow-up

Prepared driver: `filtered-followup.py`. It has only been syntax-parsed; no workload has been launched.

The preceding three-pair Kyle matrix contains a consistent filtered-listing signal that should not be dismissed as the formatter's small local cost:

| Pair | Order | Baseline | Candidate | Candidate minus baseline |
| --- | --- | ---: | ---: | ---: |
| 0 | baseline, candidate | 2.000679 s | 2.137684 s | +137.005 ms |
| 1 | candidate, baseline | 1.885645 s | 2.019021 s | +133.376 ms |
| 2 | baseline, candidate | 1.866157 s | 2.097709 s | +231.552 ms |

Host I/O-full stall increments are 1.5–4.6 ms for those six commands. They do not explain the observed difference. Expanded listing is less consistent: paired deltas are −235.316, +242.016 and +149.524 ms. Neither series establishes which phase changed.

## Prepared scope

Exactly 20 local-only commands against the same retained frozen engine and the existing restored `ux-local-production-v2/greetings` workspace:

- Two excluded warmups, one per binary.
- Eight alternating baseline/candidate pairs of the exact filtered listing.
- Two separate diagnostic commands, one per binary, with engine wcprof and CLI CPU/runtime trace capture. These wall times are excluded from the paired comparison.

The CLI is unchanged between comparison arms except the already built source differences: the previous frozen baseline and validated production CLI. The driver verifies their hashes against the previous trial, verifies the exact owned engine ID and frozen binary, reuses the audited isolated empty config, disables all Cloud/OTLP/analytics paths, and checks exact stdout bytes every time. It never mutates the workspace. Key source hashes are checked before/after.

## Controls and boundaries

- No build, engine restart, cache clear, workspace copy, source rewrite or preliminary listing inside the measured loop.
- Fresh CLI processes; exact exit timestamps come from a dedicated blocking waitpid thread. Output is collected in memory and persisted after exit. The timer includes process creation and observer scheduling.
- Before/after counters capture host and engine CPU/I/O/memory pressure, engine CPU/throttling and I/O, and child CPU time, faults and context switches. They are outside the CLI timer; there is no concurrent sampling workload.
- Paired differences and execution order are retained rather than comparing only separate medians.
- The two combined profile captures are diagnostic: `CPUPROFILE`/runtime tracing adds its own overhead, especially shutdown. Compare engine phases/counts and CLI CPU stacks; do not infer ordinary CLI exit costs from their wall time.
- The intended first decision is whether the filtered-listing slowdown persists across eight alternating pairs. If it does, locate it in CLI CPU/startup, additional engine operations, engine CPU, or waiting using the two independent diagnostic captures. Do not ascribe it to the tiny formatter merely because that is the visible source change.
- A useful later control, if the difference persists, is the retained formatter-only CLI between the frozen baseline and production CLI, with the same setup. This can separate formatter behavior from DiskWriter/build effects. It is not added to the prepared 20-command scope automatically.

All resulting data remains explicitly local-only, warm retained-engine data. It must not be mixed with normal Cloud-enabled or fresh-volume cold timings.
