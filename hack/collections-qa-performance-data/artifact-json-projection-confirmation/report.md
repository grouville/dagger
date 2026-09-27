The focused artifact-list confirmation is effectively flat: baseline median **1,144.3 ms**, projection median **1,146.6 ms**. The median paired difference is **+0.28 ms** and mean paired difference is **−1.13 ms**. This establishes no artifact-list speedup, and the earlier three-pair apparent regression did not reproduce as a consistent variant effect.

All sixteen local commands matched the exact ordered artifact golden from the preceding trial. Four explicit primers were followed by six alternating pairs. Both CLIs used the same engine, baseAddress module, configuration and restored source path from the original thirty-eight-call comparison. There were no new source edits, profiles, Cloud calls or builds. All fixture and engine cleanup checks passed; the original engine/init remained untouched and stopped, and the retained volume was preserved.

| Pair | Order | Baseline | Projection | Projection − baseline |
| --- | --- | ---: | ---: | ---: |
| 0 | baseline, projection | 1,125.0 ms | 1,137.9 ms | +12.9 ms |
| 1 | projection, baseline | 1,163.5 ms | 1,151.2 ms | −12.3 ms |
| 2 | baseline, projection | 1,117.6 ms | 1,149.0 ms | +31.4 ms |
| 3 | projection, baseline | 1,199.7 ms | 1,128.8 ms | −70.8 ms |
| 4 | baseline, projection | 1,124.1 ms | 1,192.1 ms | +68.0 ms |
| 5 | projection, baseline | 1,180.1 ms | 1,144.1 ms | −35.9 ms |

The second command is slower in all six pairs, whichever CLI it uses. With this alternating-pair schedule, the first command follows the same CLI as the preceding command and the second switches CLIs. Position and switching effects are therefore not independently identifiable. The observations do not prove an OS page-cache, network or GC cause. No engine writes were recorded inside the twelve warm command intervals; this does not account for all activity outside those intervals.

Baseline spans 1,117.6–1,199.7 ms with sample standard deviation 34.3 ms; projection spans 1,128.8–1,192.1 ms with standard deviation 21.9 ms. Six samples per arm are too few to promise reduced variance. The raw values, chronology, CPU/I/O/pressure counters and restoration results remain in `numeric.json`.

Together with the preceding matched profiles, the result supports adopting the small removal of an unnecessary request. The evidence for that mechanism is separate: six main-client requests become five, every executed operation class retains its count, and the observed catalog-to-expansion handoff drops from 24.3 to 2.8 ms. The original check/generator samples show modest savings. The supported claim is less redundant work with passing correctness gates; a broad command-speed improvement, production Cloud result or achievement of 500 ms is not established here.
