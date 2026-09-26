# Identical-binary control

Both labels use the same production CLI, SHA-256 `0c841d64a3aad06b082ad9bb0beb618f6d07e86e8ce83008e5621e7b878e86bb`. All 14 calls (two excluded warmups and six alternating pairs) return the exact expected one-line listing. The source remains unchanged.

The median paired difference is -18.3 ms. Individual paired differences range from -252.0 to 293.1 ms. This establishes that the unchanged engine/workspace can produce differences on the scale of the earlier apparent regression. It does **not** prove the two different CLI binaries have identical performance.

Engine `TotalAlloc` increases by a median **574.3 MB (547.7 MiB) per measured command**, range 569.8–598.5 MB. These process-wide counters include any concurrent engine/background activity and the small diagnostic requests; they are not allocations attributed exclusively to the filtered GraphQL query. MemStats reads bracket commands and are outside their wall timer.

| Command | CLI seconds | Engine CPU seconds | Allocated MB | Completed GC cycles | Stop-the-world pause ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| warm/00-0-baseline | 1.951 | 3.513 | 576.1 | 1 | 0.143 |
| warm/00-1-candidate | 1.947 | 2.578 | 598.5 | 0 | 0.000 |
| warm/01-0-candidate | 2.274 | 6.381 | 569.8 | 1 | 1.768 |
| warm/01-1-baseline | 1.981 | 2.694 | 574.1 | 0 | 0.000 |
| warm/02-0-baseline | 1.852 | 2.620 | 575.3 | 0 | 0.000 |
| warm/02-1-candidate | 2.130 | 6.181 | 580.3 | 1 | 0.188 |
| warm/03-0-candidate | 1.912 | 2.877 | 574.5 | 0 | 0.000 |
| warm/03-1-baseline | 1.945 | 2.599 | 580.3 | 0 | 0.000 |
| warm/04-0-baseline | 2.204 | 6.048 | 572.0 | 1 | 0.091 |
| warm/04-1-candidate | 1.952 | 2.802 | 573.1 | 0 | 0.000 |
| warm/05-0-candidate | 1.878 | 2.699 | 571.2 | 0 | 0.000 |
| warm/05-1-baseline | 2.050 | 5.846 | 570.6 | 0 | 0.000 |

Four GC cycles complete during the measured command intervals; no forced cycles are recorded. The largest stop-the-world increment is 1.768 ms. `NumGC` counts completed cycles, while mark/sweep/assist work can run across these sampling boundaries. The last command consumes 5.846 engine CPU-seconds with no completed cycle. Therefore neither a zero cycle delta nor the small pause time rules out concurrent GC cost, and neither establishes it. A CPU profile must identify the work.

The next diagnostic should attribute allocation stacks and engine CPU using the existing endpoints, without changing GC settings, forcing a collection, changing API behavior, or folding profiled times into the main benchmark. Allocation profiles are sampled and may lag by up to two GC cycles; `TotalAlloc` remains the amount reference while profile deltas identify likely allocation sites. No causal claim about the previous formatter/export changes is warranted yet.
