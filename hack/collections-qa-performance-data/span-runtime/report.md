# Span fan-out: useful allocation reduction, held after a generation regression

**The span optimization remains isolated and is not adopted.** It passes semantic/race tests and avoids demonstrable duplicate encoding, but warm native generation was slower in all three real CLI pairs. This does not yet satisfy the cross-command performance goal.

The change serializes each span snapshot once before distributing it to its local client/ancestor stores, and resolves each distinct origin once per export batch. The old path serialized the same snapshot independently for each target. The candidate preserves origin/ancestry validation, per-target row IDs, live/final order, storage errors and all delivery joins. It does not change Cloud exporters, call-payload routing, the row format or caching policy; no route cache survives an export batch.

This changes expensive serialization work from roughly snapshots × targets to snapshots, while the necessary target-specific row append/index work remains. A root-only span already has one target; the common-case path avoids imposing a route map and an extra goroutine on it.

## Compared builds and measurement boundary

Both engine variants use source `21939e4ff95dd2be7c584b883b39c5e75b20d703`, including the metric-shutdown fix, plus the same frozen experimental SDK/schema/Dang/pending-file stack. Only `engine/server/telemetry.go` differs between ordinary engines. Both use the identical ordinary CLI built from `341595f376`. The anonymous route-counter build is separate and excluded from timing comparisons. Exact binary/source hashes are in `provenance.json`.

There were **32 ordinary Cloud-connected invocations**, arranged as 16 alternating pairs, and 12 local setup/diagnostic invocations. Every command passed its actual output/correctness checks. Engine volumes were fresh at setup; identical per-flow warmups ran before ordinary measurements. Therefore these comparisons are **warm and warm edit-loop measurements, not cold-start results**. Commands were timed from process spawn through blocking waitpid. No shorter shutdown timeout, cache-budget override or forced GC was used.

`list -a`, workspace file navigation and a real selected Go unit check exercise Kyle's greetings workspace. Generation uses an independent native Dang generator that writes current input contents; it is not SDK code generation. Edited-generation pairs use fresh, identical bytes across the two isolated engines. The original fixtures were restored and verified.

## Full command outcomes

| Flow | Pairs | Baseline median | Candidate median | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `dagger list -a` | 5 | 2.280 s | 2.129 s | Mixed: candidate faster in 3/5, including one +1.166 s adverse outlier |
| `dagger ws ls` | 3 | 0.563 s | 0.560 s | Essentially flat |
| Warm native `dagger -y generate` | 3 | 0.729 s | 0.824 s | **Slower in all three pairs** |
| Edited native `dagger -y generate` | 3 | 0.931 s | 0.923 s | Small, mixed difference |
| Selected `TestFormatResponse` check | 2 | 2.407 s | 2.232 s | Too few, mixed pairs to establish a general improvement |

Every raw ordinary pair is retained below and in `paired-results.json`, including the negative results. CPU/allocation counters cover a slightly wider bracket than CLI wall time and can include background work; they are not exact per-command attribution.

For warm generation, median engine CPU rises from 0.214 to 0.582 CPU-seconds. Candidate GC occurs in 2/3 runs versus 1/3 baseline runs. This does not establish a causal CPU regression in the encoder: the no-GC pair uses 0.214 → 0.226 CPU-seconds, and the GC/counter boundary includes background work. It does establish that the overall result cannot be presented as a clean performance win.

## Where the warm-generation delay occurs

Existing engine logs identify one foreground Cloud-flush phase for all 44 commands. In the three warm-generation pairs, that phase grows **281.7→416.0**, **300.9→355.6**, and **309.1→349.9 ms**. The local telemetry flush remains only **0.10–0.52 ms**.

The no-GC pair is +77.9 ms slower overall, including +54.7 ms within Cloud flushing; generated output is observed 2.9 ms earlier, within the 5 ms polling granularity. In the other two pairs, output appears +53.4/+42.2 ms later as well. Stop-the-world pauses are only about 0.059 ms on those candidate runs; concurrent GC/assist costs remain possible but unproven.

The phase includes queue draining, HTTP completion and the refresh-file gate. These logs do not isolate network RTT, server latency, request counts or why scheduling changed. Producer timing can change Cloud batching even when exporter code is unchanged. The artifact outlier, meanwhile, adds 1165.9 ms overall but only 14.3 ms to this Cloud phase, so a single shutdown explanation does not cover the whole trial. See `shutdown-attribution.md` and paired phase values for the exact limits.

## Real route counts, separate from timing

A separate local-only diagnostic engine observed these counts until one second after the profiled command exited:

| Counter | `list -a` | Selected check |
| --- | ---: | ---: |
| Export batches | 26 | 23 |
| Input span snapshots | 3,401 | 1,626 |
| Validated target copies | 4,318 | 2,534 |
| Snapshots with one target | 2,752 | 1,058 |
| Unique origins summed across batches | 54 | 41 |
| Batches with one origin | 10 | 12 |
| Batches with fan-out | 18 | 15 |
| Batches whose snapshots all have one target | 8 | 8 |
| Incomplete-route batches | 0 | 0 |

These are routing attempts, **not Cloud request counts, durable acknowledgements or distinct logical spans**: live/final updates count as snapshots. The 917/908 extra target copies show that duplicate local encoding exists in actual user flows. They also show that most inputs still have only one target: about 81% for listing and 65% for the selected check. A synthetic three-target benchmark is therefore not representative of every snapshot.

If the same stream were serialized once, potential serialization work would fall from 4,318 to 3,401 encodings for listing and 2,534 to 1,626 for this check; per-target append/index work remains. These are structural opportunity counts, not measured wall-time gains. `routing-counts.json` includes complete batch-size buckets and provenance hashes. This trial did not collect route distributions for the slower generation flow.

## Correctness and upstream status

The baseline passes 14 semantic tests; the candidate passes the same set plus the encode-once witness. That witness fails on baseline with three Resource reads for a single snapshot delivered to three stores, and passes on candidate with one. Nine new top-level tests also pass the race detector. They cover ancestor/sibling authority, validation before writes, invalid encoding and valid siblings, retained store errors, independent target IDs, concurrency, persisted/reopened rows, links/indexes, live/final updates, origin stripping and per-batch route revalidation.

Earlier bounded microbenchmarks demonstrate allocation reductions for deeper routes, with some root/large cases effectively flat. They are not a substitute for this real CLI gate. The candidate also changes the meaning of an existing debug write-duration field from target-only preparation to shared preparation-through-append; that diagnostic boundary needs clarification before upstreaming.

The next discriminating experiment is matched local-only warm generation with query/output timing, then separate Cloud diagnostics with actual export counts and queue/HTTP timing. Until that resolves the negative generation outcome, the code stays a reversible prototype. The 500 ms goal is not achieved by this span change.

## All ordinary pairs

| Flow | Pair | Baseline ms | Candidate ms | Difference ms |
| --- | ---: | ---: | ---: | ---: |
| artifacts | 0 | 2927.9 | 2637.5 | -290.3 |
| artifacts | 1 | 2023.5 | 3189.4 | +1165.9 |
| artifacts | 2 | 2107.7 | 2128.5 | +20.8 |
| artifacts | 3 | 2279.7 | 2046.5 | -233.2 |
| artifacts | 4 | 2391.5 | 2126.6 | -264.9 |
| workspace-files | 0 | 580.6 | 527.4 | -53.1 |
| workspace-files | 1 | 562.5 | 560.3 | -2.2 |
| workspace-files | 2 | 556.8 | 563.8 | +7.0 |
| generate-warm | 0 | 717.7 | 926.4 | +208.7 |
| generate-warm | 1 | 739.5 | 817.5 | +77.9 |
| generate-warm | 2 | 728.6 | 824.2 | +95.6 |
| selected-check | 0 | 2688.0 | 2328.4 | -359.6 |
| selected-check | 1 | 2126.4 | 2135.5 | +9.1 |
| generate-edit | 0 | 1022.8 | 910.8 | -112.0 |
| generate-edit | 1 | 921.3 | 926.5 | +5.2 |
| generate-edit | 2 | 931.1 | 923.4 | -7.6 |
