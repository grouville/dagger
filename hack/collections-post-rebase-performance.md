# Collections after the main rebase: Cloud shutdown and disk variance

September 25, 2026. A direct comparison of the preserved historical build and
rebased builds confirms a warm regression. The historical build measures
**2.363 s**, the rebased baseline **2.867 s**, and the committed Cloud batching
change **2.662 s**. These are eight-run medians of the complete
`dagger check -l --all` process on greetings-api. The change recovers about
205 ms, or 7% of the rebased command time. The 500 ms objective remains open.

## Comparable builds and results

The app is `kpenfound/greetings-api@14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`,
with `dagger/go@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. Its original
backend/service/cache settings remain in place. All variants use the complete
experimental stack: Dang syntax caching, split TypeScript imports, prebuilt
TypeScript SDK runtime, Node/tsx caches and the direct Node loader. These
absolute timings are **not measurements of an ordinary branch build**.

Both historical executable checksums match the archived evidence. The new
baseline is `9e884acb8f`, rebased onto main `d8f1f0d6d2`. The retained change is
[`1b18e58b86`](https://github.com/grouville/dagger/commit/1b18e58b86).

Two warmups per variant precede eight measured runs, reversing variant order
on alternate rounds. Every run launches a new CLI, keeps Cloud telemetry and
analytics enabled, includes CLI exit, and checks all 14 output rows byte for
byte. There is no compilation or profiling during the timed series. The
broken SSH agent variable is omitted equally. Host full I/O pressure never
exceeds 13 ms per measured run in this series.

| Build | Median | Range |
| --- | ---: | ---: |
| Preserved pre-rebase build | 2.363 s | 2.301–2.472 s |
| Rebased baseline | 2.867 s | 2.815–3.078 s |
| Rebased + Cloud payload batches of 512 | 2.662 s | 2.426–2.769 s |

The previous 2.290 s median remains valid for its earlier measurement. It is
not the current rebased baseline. Remeasuring that exact build distinguishes
about 504 ms of regression in this series from the difference between hosts,
times of day or remembered historical numbers.

## Where the extra time goes

Separate wcprof captures report engine trace spans of 1.84 / 1.88 / 1.83 s,
respectively, with no dropped events or open operations. The discovery work
is similar. CLI synchronization profiles expose the shutdown difference:

| Wait in one profiled invocation | Historical | Rebased | Rebased + 512 |
| --- | ---: | ---: | ---: |
| Engine shutdown request | 6.79 ms | 666.67 ms | 433.96 ms |
| Subsequent CLI telemetry close | 393.12 ms | 134.72 ms | 117.01 ms |
| Sum of these sequential waits | 399.91 ms | 801.39 ms | 550.97 ms |

These are individual profile observations, not the medians above. They are
blocked elapsed time, not CPU usage, and cannot allocate every millisecond of
the median regression. Network duration varies. wcprof alone does not cover
the full CLI shutdown.

The ordering is explicit in `withEngine`: cleanups run in reverse registration
order. First `Client.Close` waits for the engine's shutdown response. The
engine flushes session Cloud telemetry before releasing attachables, which a
credential refresh can still need. Only afterward does `cleanupTelemetry`
close stdio, end the CLI root span, and call `telemetry.Close`. Ending the root
span creates final CLI telemetry that needs its own export. Moving the engine's
publishing out of the CLI therefore did not remove every CLI export or make
the two shutdown boundaries overlap.

## The retained improvement

Cloud call payloads previously reused the local client DB's limit of 128
records per export. Payloads and ordinary Cloud logs share a serial exporter,
so this creates additional network round trips during recipe bursts. The
payload processor now accepts an optional export batch limit; Cloud uses 512,
matching the ordinary Cloud log limit. The local client DB default stays 128.

Diagnostic warm runs of this workload contain about 1,450 payload records:
15–16 payload batches become 9–10, and total log-export calls fall from 27–29
to 18–20. The largest observed candidate payload body total is about 78 KB;
this is not total encoded HTTP request size. These counters count exporter
calls, not possible HTTP retries inside the OTLP exporter.

This is a constant-factor reduction in network work, not a new asymptotic
algorithm or a result-cache change. Ingress retains its existing lossless
queue, retries and finite retry limit; failure order, the five-second shared
Cloud shutdown budget, and waiting before process exit remain in place.
Focused telemetry/server tests pass, including delivery, retry ordering,
queue overflow isolation, cancellation, fallback and token refresh. Batch and
retry tests cover the larger limit and invalid values.

A separate source-edit validation changes `main_test.go` and launches the
same user command. Each renamed test must appear under its new name and the
old name must disappear; restoring source restores the exact original output.
These are single observations, not an edit-performance distribution:

| Edit | Rebased baseline | With 512 |
| --- | ---: | ---: |
| Comment, same keys | 3.028 s | 2.974 s |
| Rename test | 3.047 s | 2.921 s |
| Restore source | 2.943 s | 2.631 s |

## Experiments not adopted

Increasing Cloud payload coalescing from 5 to 100 ms did not give a convincing
additional gain. It also changed how the two paths interleaved; the longer
delay is not enabled.

A second prototype gives payloads and ordinary logs distinct exporters and
writer/sequence IDs, sharing the same credentials and HTTP connection pool.
Each exporter remains serial, while both paths can run concurrently. The
existing focused Cloud tests pass, but eight alternating pairs measure
**2.698 s with the shared exporter versus 2.750 s with separate exporters**.
It does not demonstrate a speedup. Its patch is archived, not enabled.

Safely overlapping the engine and CLI shutdown boundaries is a different
change. It needs a distinction between engine work completion and Cloud drain
completion. The CLI could finalize its own trace at the former boundary,
while engine exporting continues, then wait for both drains before exiting.
That requires preserving final logs, status, frontend delivery, cancellation,
credential access and fallback behavior. Simply ending the CLI before its
export goroutines finish does not provide that behavior. No such protocol
change is included here.

## Cold disk variance survives benchmark cleanup

Thirty-two task-owned benchmark engines had remained running with no active
sessions. Their cgroups together held about 14.54 GiB of memory, including
file cache, and 2.59 GiB of swap. They were stopped cleanly, preserving their
containers and volumes; unrelated engines were left alone. Those figures are
not process RSS or proof of a memory leak.

Engine images are now prepared once outside the timing loop. Each cold run
uses a new empty Dagger volume on a ready engine, with one benchmark engine
active at a time. The host page cache is retained; engine image download and
provisioning are excluded. No remote result cache is used. Disk/PSI samples
stay in memory until the timed command finishes. We did not change global
writeback settings, drop caches, remove fsync, or delete stored results.

The unprofiled cold runs use a balanced before/after/after/before order:

| Order | Build | Command | Host full I/O stall | Engine full I/O stall | Device mean write await |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Baseline | 27.145 s | 0.189 s | 0.050 s | 2.5 ms |
| 2 | 512 | 27.255 s | 0.254 s | 0.064 s | 3.3 ms |
| 3 | 512 | 47.845 s | 18.059 s | 11.631 s | 84.0 ms |
| 4 | Baseline | 45.448 s | 16.902 s | 11.930 s | 103.4 ms |

Every cold output is correct. The batch change does not demonstrate a cold
speedup. Both versions encounter the slow disk regime. Full I/O PSI is a
pressure measure; it is not a disjoint part of command time to subtract.

The root NVMe writes a similar 1,591–1,672 MiB in each sampled interval, but
its recorded busy time changes from 1.30–1.52 s to 33.64–37.98 s. The engine
cgroup accounts for 1,461–1,547 MiB of writes. Host dirty pages start below
1.6 MiB in every run, and swap traffic is below 0.2 MiB per run. Thus these
slow samples are not explained by active swapping or a large backlog of dirty
host pages at command start. Device-level write latency is the stronger lead;
filesystem/journal and device-internal effects still need separation.

The device identifies as `INTEL SSDPEKNW020T8`. Internal flash/cache behavior
is a hypothesis, not a measured cause: an [Intel-hosted study of the 660p](https://www.intel.com/content/dam/www/public/us/en/documents/white-papers/shrout-research-cost-benefit-analysis-qc-flash-white-paper.pdf)
describes dynamic SLC caching, but our Linux counters cannot establish whether
that cache was depleted. A later temperature reading was about 37°C, not a
continuous thermal trace of the slow samples.

A separate fsync/fdatasync trace found 130 calls totaling 390 ms, with a maximum
of 40 ms. That run had low disk pressure. Ptrace stretched the command to
50.14 s, so its wall time is excluded from comparisons; it does **not** explain
fsync duration on the slow-disk runs. It gives no reason to remove durability
operations. Earlier tracing attempts failed to attach; their timings are not
fsync evidence. Initial incomplete-prototype runs are also excluded because
they omitted the prebuilt TypeScript engine wiring.

Practical mitigations are to reuse the persistent engine in the normal dev
loop, avoid concurrent bulk imports/builds on the same device, and reduce the
bytes written by discovery. Moving only disposable compiler scratch into a
normal Dagger temporary mount is a possible experiment; persistent build
caches and outputs would remain intact. That prototype was built but not
benchmarked and is not enabled. The distributed cache can eliminate compatible
builds, but does not make required local materialization or writeback free.

Stopping obsolete engines releases their live resources but does not reclaim
volume space. A Docker-wide size inventory was too expensive and was canceled;
no volume-size total or disk-space reclamation is claimed. All benchmark
engines from this investigation are stopped, and all their volumes retained.
Disk variability remains unresolved rather than hidden by selected samples.

## Evidence

[Raw timings, counters, scripts, checksums and rejected prototype](collections-qa-performance-data/post-rebase/)
include both comparison series and all four cold samples. Large binary,
profile and raw sampler files remain under `/tmp/collections-perf/post-rebase-io`
with hashes in the archive. The historical reports and their original results
are unchanged.
