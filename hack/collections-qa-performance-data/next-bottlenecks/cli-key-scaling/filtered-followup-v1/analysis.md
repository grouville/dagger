# Filtered listing: unresolved latency signal and next control

All 20 commands passed exact-output checks. Eight unprofiled pairs retain a slowdown signal: separate medians are 1.9346 s baseline and 2.0739 s candidate; median paired difference is +212.0 ms, with the candidate slower in six of eight pairs. Do not publish a blanket whole-command speedup from these changes.

CLI CPU medians are close: 0.5188 versus 0.5357 CPU-seconds. No engine cgroup throttling occurred. Host/engine I/O-pressure increments are only a few milliseconds.

The engine CPU counter shows two regimes. Using 4 CPU-seconds only as a descriptive split between the observed clusters:

| Binary | Lower-CPU commands | Lower-CPU median wall | Higher-CPU commands | Higher-CPU median wall |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 6 | 1.9025 s | 2 | 2.1381 s |
| Candidate | 4 | 1.9545 s | 4 | 2.1787 s |

The lower cluster consumes about 2.6–3.1 engine CPU-seconds per command; the higher cluster consumes 5.2–6.1. Both candidate-faster pairs put the higher cluster on the baseline command. This suggests periodic work, with GC a candidate, but the residual lower-cluster medians still differ by about 52 ms and this data does not prove a complete explanation.

## Separate diagnostic profiles

The profiled order reverses the apparent regression: candidate 2.028 s, baseline 2.218 s. Those wall times include profiling overhead and are excluded from the unprofiled comparison.

Both wcprof files contain exactly 17,251 operations and 234 served queries. Operation counts by kind/class are identical. The only outcome differences are small swaps between `hit` and `joined` in ten call classes; executed-body counts do not increase. Both invoke the same six `/runtime` processes.

The slower baseline profile consumes 5.897 engine CPU-seconds; candidate consumes 2.667. Two `/runtime` spans stretch from approximately 93/104 ms to 160/171 ms. Total `session.serveQuery` interval union grows from 1.819 s to 2.007 s. CLI CPU profiles contain 340 ms and 360 ms of samples respectively, with no evidence of a formatter taking hundreds of milliseconds. Nested phase durations are not additive.

The current evidence identifies extra engine work or waiting during periodic high-CPU commands. It does not establish a source-level regression or absolve either patch.

## Prepared control

The extended `filtered-followup.py` supports:

```
python3 filtered-followup.py --run --trial filtered-identical-memstats-v1 --pairs 6 --identical-bin --memstats
```

This is prepared, not executed by the reviewing agent. It performs exactly two excluded warmups and 12 measured commands, using the same production binary under both alternating labels. It reuses the same workspace, audited local-only environment, and frozen engine. There are no separate profiler commands in identical-binary mode.

The existing `/debug/vars` endpoint provides MemStats. Before/after snapshots retain only a fixed numeric allowlist, including NumGC, NumForcedGC, TotalAlloc, HeapAlloc/HeapObjects, NextGC, PauseTotalNs and GCCPUFraction. Raw expvar output is not saved. There is no `/debug/gc` call and no change to GC or cache settings. Read duration is recorded; the diagnostic endpoint itself has some allocation and synchronization overhead outside the CLI timer.

This control asks whether the two CPU regimes and apparent label differences occur with identical code, and whether GC increments track them. An engine CPU profile would still be needed to attribute GC CPU time rather than infer it from NumGC and cgroup CPU. Only after that should a formatter-only or same-basename comparison be added if a binary-specific residual remains.
