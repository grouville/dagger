# Main-client telemetry completion

Status: correctness fix validated; no demonstrated Rust speedup. The performance
goal remains unmet. This branch is independent and based directly on upstream
`7c35e6274737acff0f6bd76614abb5e04efa7d12`; it does not activate the separate
containerd/image-stream prototype or the unpublished URL-resolution lock.

## Context and fix

An ordinary `dagger --profile check rust:check` returned successfully, but its
raw exported trace lacked `wcprof.session_complete`. The maintained analyzer
correctly refused to certify completeness. All 191 received spans had start/end
records, including 173 marked engine spans; the carrier was missing from raw,
not just extraction. The other 27 command traces in that capture had a carrier.
The receiver continued through five later commands, ruling out its final stop.

Engine logs show `/shutdown` finished at 13:59:38.870 UTC, background session
removal started at .880, and the final two carrier rows entered the DB at .882.
The endpoint closed the main client's subscriber channel before background
teardown stamped the exact final count. An empty DB read could therefore end
the SSE stream before the carrier arrived.

Keep nested-client shutdown independent, but close the main subscriber only
after all session telemetry providers finish. Separate that barrier from
container releases; do not wait for container, analytics or egraph cleanup to
permit telemetry EOF. Preserve asynchronous HTTP shutdown, the existing final
count and query drain, session tombstones, authorization and resource ownership.
No sleeps, fabricated markers, weaker analyzer gate or new cache policy.

## Correctness reproduction

From this branch, using its Go toolchain:

```sh
go test -race -count=3 -run 'Test(MainShutdownKeepsTelemetryUntilSessionComplete|NestedShutdownStillClosesOwnTelemetry|MainTelemetry.*|MainClientLastDisconnectDoesNotBlockOnTeardown|SameIDConnectDuringBackgroundTeardownGetsRetryable|Reap.*|Concurrent.*Teardown.*)$' ./engine/server

dagger api call engine-dev test --pkg=./core/integration --run='^Test(Telemetry|Engine)$/^Test(InternalVertexes|ConcurrentCallContextCanceled)$' --parallel=1 --timeout=15m --count=1 --test-verbose=true
```

Copy the new test file to a separate checkout of the parent, then run
`TestMainShutdownKeepsTelemetryUntilSessionComplete` alone to reproduce the
early-close failure. It fails deterministically before production changes.
Do not revert an existing working tree to reproduce it.

Executed validation:

- Baseline fails with `main telemetry closed before the session-complete carrier
  was emitted` (0.370s test runtime, not build time).
- Focused candidate race/count 3 passes in 1.513s. It includes real DB-backed SSE,
  actual asynchronous last-disconnect cleanup, exact span-count reconciliation,
  blocked main/nested provider shutdown, errors and duplicate/nested shutdown.
- Source-built integration selection passes both methods; independent raw
  replay validates five unique case identities including suites/subcase.
  Invocation: 142.974s including provisioning/building, not a Rust benchmark.
- Publication adds blocked-container-release and reconnect channel tests;
  its focused race/count 3 passes in 1.511s. Only a field comment differs in
  production from the source-built and benchmarked candidate.

The SSE unit test invokes the real subscribe handler directly; HTTP routing's
exclusion from ordinary-client active counts is established by source review
and the separate ordinary-CLI runs, not by that unit test alone. A stuck query
drain or surviving ordinary connection can still delay session completion;
this patch does not introduce a universal shutdown deadline. Late independently
admitted OTLP writes are not claimed solved.

## Ordinary CLI latency check

One retained control/candidate engine pair; identical CLI, local Rust module,
toolchain, flags and pinned ripgrep source. Six balanced AB/BA exact cycles and
three matched novel application edits, plus first module/prime/profile/failure/
repair: 28 separate CLI processes. No listener. Fresh per-arm source, target,
registry and XDG namespaces. All commands export local telemetry. Exact headline
calls omit `--profile`; application/failure/repair and separate companions use it.

The first candidate latency capture overlapped a local checkout; retained as correctness evidence,
not a clean latency comparison. The complete repeat below ran after builds,
tests and checkouts had finished, with fresh cache namespaces and new edits.
Both captures pass 28 actual-command checks and 16 maintained wcprof gates each.
Repeat profiles reconcile declared/received engine spans exactly; replay drift
is 0.0 to -0.1%. Actual app edits rebuild only ripgrep 15.2.0; deliberate failures
execute Cargo and exit 101; repairs succeed. Both primes select bstr 1.12.0.

Milliseconds; positive paired saving favors candidate. Paired medians need not
equal the difference between marginal medians. Keep all observations/outliers.

| Flow | Control median [min,max] | Candidate median [min,max] | Paired saving [min,max] | Favorable |
|---|---:|---:|---:|---:|
| Exact cached check |511.769 [508.210,594.344]|511.760 [490.754,524.879]|5.886 [-6.367,76.869]|4/6|
| Application edit |900.153 [879.074,1008.941]|905.506 [883.526,907.868]|16.627 [-28.794,103.435]|2/3|
| Deliberate compile failure |851.799|858.810|-7.011|0/1|
| Repair/revisit |518.100|486.819|31.282|1/1|

This is a latency-impact pilot, not a statistically established speedup or
equivalence result. The marginal edit median is slightly worse. It does not
establish Cargo parity, cold-start improvement, a complete installed stack,
artifact/export performance, macOS, remote-engine or general concurrency speed.
First-module/prime are setup observations, not cold comparisons. Both runtime
arms inherit the same separately documented verified-stream/Unix-ready prototype;
only this branch's three tested source paths differ. `cleanup=false` protects
unrelated engines; ordinary CLI startup/session/shutdown remain timed.

## Exact local evidence and identities

Retained owner: `/tmp/dagger-profile-completion.jV5kzLqs`.
The frozen repeat is `pilot-r2/`: `capture.py --preflight`, then `capture.py
--execute`, then `analyze.py`. These controllers refuse to overwrite a prior
attempt; replication requires a fresh reviewed output namespace/cache key.
Module bytes come from the benchmark fixture published at grouville/dagger
commit `b5070c47a3458a535294d13a212f2cd2d221c757`, used locally here.

- Parent upstream: `7c35e6274737acff0f6bd76614abb5e04efa7d12`.
- CLI SHA256: `6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad`.
- Control image: `sha256:5d660298fd273eec4facabca4b1ecaf56cac7bc2342aaf3eec6a6d26ff1bb8da`.
- Candidate image: `sha256:1cc1d7e14f1facf8aa9dde08750083701f33e02281cf206b13a3235361263b67`.
- Capture controller: `36794eef7e1bedf7413cdbf120fcc32b589350ef9294e7a32fa8f412845086dc`.
- Audit controller: `e92dc307ee368641dd5484630af754a2185e143b5100f12b49c4d8f94e346eec`.
- Repeat report: `8d5829189b875d1814511cf5c56d59cb9860723afd10796769cdb28fd592858e`.
- Repeat raw: `60d59849b78fa8e7069992671a631375beafb5170bf645f13ceef08564194359`.

Raw telemetry, binaries and the private maintained wcprof executable are not
published. The local evidence retains every command, source/config/lock hash,
actual Cargo execution, selected package/version, receiver and engine identity.

## Branch navigation

New confirmed work uses `perf/`; old experiment branches are preserved.

| Branch | Parent / relationship | Status |
|---|---|---|
| `perf/rust-23-telemetry-completion` | Direct upstream 7c35; independent fix | Correctness validated; no demonstrated speedup |
| `experiment/engine-unix-readiness` | `experiment/cli-engine-inventory` | Previously published; separate runtime fix |
| `experiment/cli-engine-inventory` | `experiment/client-readiness-current` | Previously published CLI discovery improvement |
| `experiment/current-main-verified-image-stream` | Separate experimental stack | Published inert patch/evidence, not enabled here |
| URL-resolution identity lock | Still local; future independent `perf/` change | Promising pilot, not yet confirmed/published |

Do not treat these branches as one cumulatively benchmarked or upstream-approved
stack. Cold and Rust edit-loop targets remain unmet.
