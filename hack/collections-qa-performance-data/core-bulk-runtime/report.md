The four process-restart blocks ran baseline / candidate / candidate / baseline on the same retained owned Dagger volume. All38 local commands passed their exact stdout and fixture checks; the original engine binary was restored and stopped. No Cloud calls ran.

| Flow | Baseline median | Candidate median | Difference | Samples per variant |
| --- | ---: | ---: | ---: | ---: |
| first-api-after-restart: core | 502.9 ms | 490.3 ms | -12.6 ms (-2.5%) | 2 |
| warm: core | 223.0 ms | 231.4 ms | +8.4 ms (+3.8%) | 4 |
| warm: module | 304.0 ms | 336.3 ms | +32.3 ms (+10.6%) | 4 |
| warm: listing | 1443.8 ms | 1498.4 ms | +54.5 ms (+3.8%) | 4 |

Engine process startup/stop, priming and profile downloads are excluded from ordinary timings. First API means the first command after an engine-process restart on the existing volume; persisted results can be reused. The two separate profiled commands identify construction/cache work and are not latency samples. CPU/I/O counters include any engine background work.

The preceding harness attempt is retained separately: its first command succeeded but returned the new frozen build version, while the harness still expected the old build version. It made one local command and restored the engine; it is excluded from this comparison.

These results validate the runtime behavior of the bulk consumer on this experimental SDK stack. They must be read alongside the three-pair fresh library construction benchmark; neither establishes a general improvement across all workflows. Raw numeric samples and phase counts are in the accompanying JSON.
