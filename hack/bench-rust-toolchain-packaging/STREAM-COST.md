# Cold image attribution: hashing and producer backpressure

2026-09-13. Data-only diagnostic checkpoint on perf26; **no new speedup or
production change**. The six-flow scorecard in README remains the headline.
This answers what occupies the remaining image phase before choosing a fix.

## Measurement boundary

One fresh Rust-absent engine, the same frozen 562e engine / 6a5 CLI / prebundled
module and complete standard OCI image as perf26. An empty introspection query
first provisions the engine without loading the module or Rust image. Then two
15-second engine CPU/runtime captures bracket an ordinary standalone
`dagger --profile check rust:check`. After both collectors finish, capture wcprof
and cache dumps, then run `dagger check rust:check` in a new process/session.

Preprovisioning, profiler overhead and the lack of a native comparator make this
an attribution diagnostic, NOT a cold-first-CLI benchmark or A/B improvement.
Do not add its preprovisioning timer to claim an ordinary first-command result.
The engine includes earlier experimental streamed import and pipelined hashing;
it is not clean main and excludes the separate writeback candidate. Upstream
main was reverified at 7c35e6274737acff0f6bd76614abb5e04efa7d12 after capture.

## Observations

| Measurement | Result | Meaning |
| --- | ---: | --- |
| Profiled Rust-absent check, excluding provisioning | 10639.901 ms | Diagnostic only |
| Source reconciliation + Cargo execution | 6207.309 ms | Full expected cold crate set |
| Complete image delivery envelope | 3462.772 ms | Observed, not a CPU total |
| Layer HTTP GET/body lifetime | 3189.679 ms | Includes local consumer backpressure |
| First response byte | +2.333 ms | Reused local-registry connection |
| Image-phase SHA-256 CPU samples | 361 / 745 (48.46%) | Sample share across engine goroutines |
| Uncompressed hash worker CPU samples | 268 / 745 | Inclusive stack count, not exact duration |
| Producer waiting in pipe select | 2215.711 ms | Dominant blocked-state group |
| Extractor waiting for hash buffers | 1041.998 ms | Overlaps producer/decoder work |
| Hash worker waiting for input | 710.066 ms | Not all hashing is continuously runnable |
| Final large-blob file sync | 187.095 ms | Separate retained durability operation |
| Ordinary exact follow-up | 565.366 ms | No Cargo execution; still far from goal |

CPU counts are clock-filtered runtime samples over the exact whole image
envelope, not the whole 15-second CPU profile. The latter includes module/Cargo
orchestration and idle time; it is retained separately. Waits overlap and must
not be added together or equated with potential wall-time savings. The HTTP
label is response-body lifetime through EOF/Close, not measured network cost.
CSV `producer.pipe_wait` records that select group specifically; another
3.155 ms / 539 intervals occur in pipe channel-receive waits and remain in the
full trace. Neither group is an independently recoverable wall-time saving.

This host is an Intel i5-9300H: four cores/eight threads, AVX2 but no SHA-NI flag.
The sampled Go path is SHA-256 AVX2. Do not generalize its hashing cost to Apple
Silicon or SHA-accelerated remote workers. No host capability, CPU-feature,
security, durability or digest-verification setting was changed; no sudo used.

## Validation

wcprof: 289 operations, one root, no open/dropped events; 271 declared and
received engine spans, structural PASS, replay drift -0.1% against the unchanged
absolute 2% gate. The preprovisioning trace has no image/exec work. Cold transfer
contains the full 298210801 compressed bytes with converged download/unpack
progress; actual Rustup and Cargo execution succeed. Cold crate identities match
all three prior B captures. The ordinary exact trace has no exec/image transfer.
Cache snapshot parsing passes; it is not a leak-free lifecycle proof. Owned registry/engine/volumes are removed and
the prior host resource inventory and retained engines are unchanged.

Existing maintained pprof and x/exp trace parsers read both profiles. The complete
observed image window lies within them; CPU samples exist before and after it.
Fifteen clock snapshots differ in wall/trace offset by only 207 ns. There are
745 image-phase samples, zero unknown stacks, and 1361 same-state generation
events whose original wait attribution is preserved. A terminal synthetic Sync
means parse-complete observed trace data, not proof of the requested stop time.
CPU header duration includes draining; header containment alone is insufficient.

Analyzer validation retains a rejected full synthetic 500 ms window and a
passing interior 300 ms window. That fixture is not Rust performance evidence.
Review corrected generation-status attribution and strengthened coverage gates
before interpreting this capture. Raw data was not changed. One controller-audit
retry corrected comparing launch-order receipt entries with join-order JSONL;
all entries/identities still compare exactly by unique label.

## Reproduction, identities and next experiment

Local owner: `/tmp/dagger-rust-stream-cost.UrkVsQY0`. Reviewed `capture.py --plan`
validates frozen inputs without Docker; `--execute` requires fresh owned state,
uploads the parity-verified complete OCI image to a new private local registry,
captures existing debug endpoints, and performs ownership-checked cleanup.
It deliberately refuses to overwrite earlier captures. `analyze.py` extracts
the three unique CLI traces and runs maintained wcprof/cache/correctness gates.
`profile-window-r2 --cpu cpu.pprof --trace runtime.trace --start-ns
1789337569787323354 --end-ns 1789337573250094951` selects the observed image phase.
Public CSV is a six-decimal projection of these retained inputs, not new timings.

| Retained input | SHA-256 |
| --- | --- |
| Capture receipt | 94e9f19281f00f029758ff414429ca29e332022d03387bd14a38ab2b891c88b5 |
| CPU profile | d9081e73c4f308cf5b0d5cbf0f0ddffd9b89c7ebc8d0ad6bbc81dee723b38f3c |
| Runtime trace | c66b12d268874454d5ae9b70db3bdc4f752f66390bdc5aeb0c0dc950114e0429 |
| wcprof/execution audit | 41bd0793bccece973a1e5504dd819316307c8f57868d05488a8e768a2e1433eb |
| Image-window analysis | 5a9a9c2b022d08742f70db75a4a0fc3079398c6743e97f6e7c24d26a6478038c |
| Window analyzer source | 58a213be89ce694b5b55f81e414b30dc763e8184a9f5ae559c3c4dc0d6a94022 |
| Window analyzer binary | 08fcb9d39498d5cac674d34ff4cb0a094a7da3ccd547571df003e49e368a6919 |

Next hypothesis: a bounded relay may overlap verified content writes with
decompression/application more effectively. Test it in isolation before an
engine build, then require ordinary complete-flow A/B results. Preserve all
compressed/uncompressed verification, ordered bounded ownership, cancellation
and joins, failed private-snapshot disposal, resume fallback and final syncs.
No claim that buffering eliminates 2.216 seconds or meets the cold target.

All perf26 limitations remain: preinstalled tools/images/module, local registry,
unpurged host caches, experimental engine, no full-install/public-CDN/auth,
shared-base, configuration-edit, macOS/remote or full checks/artifact matrix.
This is not yet a turnkey public runtime repro. No raw profiles, credentials,
private analyzer, public image, PR or maintainer-approval claim is published.
