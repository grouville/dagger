Numeric attribution of the completed independent-log comparison

All44 commands passed (32 normal Cloud,12 local). The historical `lazy` label in saved results means the independent-log exporter candidate, not a change to lazy-core itself. Both variants include the same lazy-core implementation. The candidate remains on hold: warm generation improves in this small series, but artifact listing and edited generation regress.

| Flow | Pairs | CLI baseline → candidate median (ms) | Main Cloud flush baseline → candidate median (ms) |
| --- | ---: | ---: | ---: |
| ordinary-warm/workspace-files | 3 | 631.8 → 579.4 | 161.2 → 166.5 |
| ordinary-warm/generate-warm | 3 | 822.2 → 723.3 | 378.4 → 246.7 |
| ordinary-new-input/generate-edit | 3 | 829.8 → 1015.6 | 340.1 → 480.6 |
| ordinary-warm/artifacts | 3 | 2033.0 → 2729.3 | 456.8 → 1132.9 |
| ordinary-warm/generators | 2 | 1732.8 → 1494.8 | 835.8 → 514.0 |
| ordinary-warm/selected-check | 2 | 2079.8 → 2035.1 | 409.8 → 384.2 |

The three artifact losses are dominated by the engine main-client Cloud flush. Flush goes398→2098,462→1133,457→941 ms; the corresponding CLI deltas outside the recorded shutdown handler are+90,+24,+10 ms. These residuals include other work and CLI cleanup; they are not pure query time. The first two edited-generation pairs show similar flush losses; the third adds only20 ms in flush and84 ms elsewhere.

This establishes where the regressions wait, not why. The ordinary engines do not expose per-request batch/record accounting. The matched passive transport diagnostics will compare actual artifact and generation request counts, bytes, overlapping requests and per-channel flush branches. More parallel writers might alter batching/backpressure; that remains a hypothesis until the counters establish it.

The observations use monotonic duration fields extracted from44 main-client shutdowns in the existing stopped-engine Docker logs. Background session shutdowns are associated privately by session identity and exported only as numeric records. Raw logs, identifiers and credentials are excluded. Parent/source/result hashes live in summary.json and numeric-phases.json. No new CLI, engine workload or Cloud request was made for this analysis.

Only3 pairs for most flows and2 for selected checks/generator listings; unequal retained-volume history and network variation limit broad claims. Source-only optimization stays isolated.
