# Single-generator snapshots: completed comparison and experiment history

## Decision

Keep the focused generic snapshot-preservation fix, not a Rust-specific cache
shortcut. Its correctness regression fails before and passes after. The
completed [stable-root 30-pair comparison](stable-root-results.md) records
649.438 ms application and 1521.509 ms library paired savings, with the merge
removed. The candidate **still loses to native Cargo by paired medians of
1152.251/1437.164 ms**. The goal is not achieved. The pilot and interrupted
attempt below remain distinct evidence, not retrospectively successful runs.

The engine fix is `38d5bbca38` (`fix(core): preserve snapshots for a single
generator result`). It is isolated on `perf/rust-17-single-generator-snapshots`.
This benchmark prototype and its limitations are separate review material.

## Provenance

- Upstream main: `fd9bc0036ad2680cc7caff3310a429e6a710eb5d`, rechecked against
  upstream before the engine commit. Baseline stack tip:
  `3f129d3b463622673bca1634f2d6bbe03e1b8b12`.
- Candidate: that baseline plus the 42-line `core/schema/generators.go` change.
  Production patch SHA256:
  `21696d6539db9fca2b917256881bdcf9e6fc94be40e6d3e96c7333862d83b803`.
- The **same** Go 1.26.8 CLI runs both sides:
  `/tmp/dagger-rust-main-fd9bc0036a-bin/dagger`, SHA256
  `86771442d5b3e4c50383f08f3fbfc57e4b2d674a4c9229bd89fbd8bc2c7f020c`.
- Baseline engine image:
  `sha256:a01c1b746fd74daeffbd9ee53ffdf9826006ae8de3768fd9d8fa454649b5919d`.
  Candidate:
  `sha256:f2af055e32f6e65fbabdbcee9561d9adc26cddb6c01f4b41b73058564847d174`.
  Both exact container IDs/images were verified running before each batch.
- Rust image: `rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b`;
  Cargo 1.97.1 (`c980f4866`, 2026-06-30), Linux/amd64, ordinary dev profile,
  debuginfo=2, incremental, no special linker. Build flags:
  `--workspace --locked --message-format=json-render-diagnostics`.
- Module main SHA256:
  `48c95bb11c503e94cda52d61f1313f458f3813714d83acd703ed8996660f4164`.
  Original measured harness SHA256:
  `6459c8e128d75c168daa5c8a442d25be42ea7b5ece43be4580f462748c7d0d71`.
  Subsequent Git-root hardening is a harness change, not retrospectively part
  of either earlier recorded run. The separate completed stable-root run uses
  the hardened harness; see its [results and audit](stable-root-results.md).
- Git-root-hardened harness SHA256:
  `fe08a74e70b60b4e16b0eb1361e11b059b9dda7e9bf6a97d006ba63491c83985`.
  Its 27 pure-Python guards pass (0.010s root validation). It initializes and
  verifies an owned module Git root before Dagger/Docker commands and isolates
  inherited Git configuration without logging potentially sensitive values.

The exact managed runner URLs were:

```text
docker-image://localhost/dagger-engine.rust-main-fd9bc0036a?container=dagger-engine.rust-main-fd9bc0036a&volume=dagger-engine.rust-main-fd9bc0036a&cleanup=false
docker-image://localhost/dagger-engine.rust-single-generator-fd9?container=dagger-engine.rust-single-generator-fd9&volume=dagger-engine.rust-single-generator-fd9&cleanup=false
```

Build/deploy used the repository dev workflow via
`--x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21`; the candidate deploy
took 1m41s, excluded from warm measurement. Native Cargo uses a separately
owned Docker container with persistent intermediate and final-output directories.
These are standalone CLI/session measurements, not a listener, but the engines
and images are already present. Readiness remains `asymmetric-or-unknown`.

## Three-pair pilot

Run `/tmp/dagger-rust-generator-pair-ebhbw1kf`. Raw process timings, including
warmups, are in [pilot-timings.csv](pilot-timings.csv). All times below are ms.

| Edit then full generate (n=3) | Native median | Before median | Candidate median | Paired saving median | Paired native overhead median | Paired candidate/native ratio median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Application | 152.134 | 1878.972 | 1192.059 | 667.410 | +1040.398 | 7.57x slower |
| Workspace library | 209.188 | 3046.359 | 1556.817 | 1489.542 | +1311.451 | 7.27x slower |

Candidate wins against before in 3/3 pairs each. Paired saving ranges are
659.337–822.364ms and 1429.969–1864.387ms. Candidate process ranges are
1151.917–1211.562ms and 1520.639–1601.602ms. No outliers were removed.
At n=3 the nearest-rank p95 is the maximum, not a useful tail estimate. Ratios
and overheads are computed per pair; subtracting separate medians differs.

One setup build per side and one warmup triple per scenario were recorded and
excluded. Each new source edit changes an observable literal. All six execution
orders occur over the whole pilot, but n=3 does not balance them within each
scenario. Native also retains normal final files; Dagger additionally performs
metadata parsing, immutable artifact selection and host Changeset export.

All eight triples including warmups pass target/freshness and behavior checks:
application edits rebuild only `prototype-app`; library edits rebuild
`prototype_library`, `prototype-app` and `prototype-secondary`. All four final
files, roughly 30MB total, are validated, including unchanged Cargo-fresh outputs.
All 32 executable comparisons are raw-byte equal. All 32 archive comparisons
are **raw-byte unequal**, but pass strict compiler-member-identifier-only
equivalence. No binary/compiler/profile normalization is used. Candidate modes
match native; 28 known baseline permission discrepancies remain recorded.

### wcprof attribution

The maintained analyzer accepts 15/16 complete timed traces. Each accepted
trace has a matching completion count, zero dropped links/open operations/
orphans/cycles/malformed waits and about -0.1% or less replay drift. Each has
exactly one successful combined rsync + Cargo + metadata action inside its
timed process. Whole CLI boundaries also include roughly 27–31ms before the
root and 10–25ms after it in measured samples.

`library-1-after`, trace `e73b5a2b3c0af2342a9331e52823a8c9`, lacks its
completion marker (declared 0, received 503). An exact-ID late rescan still
fails. Its process timing stays in the table; its causal rankings are excluded.
Do not infer absence of missing work merely because visible operations close.

Accepted sample 2 shows merge self-time of 659.5ms application / approximately
1470ms library disappearing. Actual sync/Cargo/metadata is 213.8->201.6ms and
248.2->253.2ms: no compiler-speed claim. HTTP POST count remains 30; the graph
has nine fewer operations. On application sample 1 a baseline target-upload
spike also contributes, so not every millisecond saved belongs to the merge.

Remaining candidate sample-2 costs include module runtime residual about
129/132ms, module loading 144/118ms, `diffStats` 30/199ms, previous target subtree
upload 20/104ms, host download 12/89ms and connection/startup work. These are
self-time classifications, not additive promises of critical-path savings.
Full local evidence: `/tmp/dagger-rust-single-generator-pilot-2-analysis-*`.

## The 30-pair attempt failed and remains failed

Run `/tmp/dagger-rust-generator-pair-exsdnolk` stopped at application sample 20
with `Cargo target/freshness differs`, before any library samples. Retain all
timings in [failed-30pair-attempt-timings.csv](failed-30pair-attempt-timings.csv),
but **do not present a partial-run median as a completed 30-pair result**.

Five focused complete traces pass maintained wcprof gates. Sample 20's timed
candidate builds only the application (262.966ms combined action, 1200.878ms
whole command). The subsequent diagnostic command actually executes again
(338.468ms action, 1203.549ms command), rebuilding all three targets. Sample
19's diagnostic has no actual execution.

Decoded call identity and source-import records show why these are different
actions, despite identical Cargo source, explicit cache keys, image and argv:

| Boundary | Timed build | Later diagnostic |
| --- | --- | --- |
| Local module context root | frozen `.../module` | `/tmp` |
| Relative module source root | `.` | `dagger-rust-generator-pair-exsdnolk/module` |
| Cache-volume namespace | `mod(rust.)` | `mod(rustdagger-rust-generator-pair-exsdnolk/module)` |
| Locked build volume recipe | `xxh3:3bc1749cae0e26e5` | `xxh3:91375c547ba9ffb0` |
| Cargo action recipe | `xxh3:ea843cdc2bf17edd` | `xxh3:9ee94ed7281e6ddf` |

`localModuleSource` finds the nearest ancestor `.git` for its context;
`namespaceFromModule` includes the relative module root. The context import
itself changes, not only a constructor digest. A current sandbox read sees
a protected `/tmp/.git` mount while a current escalated read sees no marker.
**The historical reason for the changed find-up result is not proven.** Do not
attribute it to aggregation, GC or egraph corruption without baseline evidence.
The next harness version initializes its own frozen module Git root and verifies
it, preserving normal namespace isolation instead of forcing a shared cache.

All retained executable hashes for sample 20 match native, but the harness
stopped before that sample's archive-equivalence and behavior validation; those
checks are not retroactively claimed. The native container was removed only
after exact ID + ownership-label verification. All files and engine caches are
retained. Local audit: `/tmp/dagger-rust-generator-failure-analysis-report.md`
and corresponding `-application-*`, `-summary.json`, `-identities.json` evidence.

An earlier pilot (`/tmp/dagger-rust-generator-pair-9uezjq3i`) also remains
failed: it required raw archive equality and stopped at its first warmup.
The later guard permits only verified internal member identifiers and has
negative tests for changed code, metadata, index, names, order, padding and
unknown extra bytes. It never rewrites artifacts to make comparisons pass.

## Correctness tests and unresolved properties

The engine commit records the full pinned dev test command. The containerized
run passes 25 tests in a 2m5s workflow: new snapshot, root `.git`/worktree-file
exclusion and skipped-module-repair cases plus existing generator/overlay/SDK
cases. New snapshot tests exercise two standalone CLI runs, binary NUL bytes,
deletion, 0600/0750 outputs, 0700 empty directories and unchanged 0664 siblings.
The pre-patch engine fails on generated permissions; candidate passes.

The extra manual [nested-cwd regression](known-issues/generators_single_cwd_test.go.txt)
is deliberately retained as a **known failing repro**, not included among those
25 passing tests. Copy its contents into `core/integration` only when investigating
the issue: a 0750 invocation directory becomes 0755 on both engines, already
visible in `currentWorkspace.directory(".").stat(".")` before aggregation.
The associated zero-selected-generators case passes. Do not weaken the 0750
expectation or describe this metadata property as fixed.

Source review: one regular no-op result retains its equal **full Before and
After snapshots**, minus root `.git`, rather than replacing both with empty
directories. This snapshot identity distinction should remain explicit even
when no host changes are exported. It is not a no-op performance measurement.

Multiple-generator metadata handling remains unchanged; solely directory or
non-executable-mode changes can still encounter existing `isEmpty` semantics.
That metadata-only `isEmpty` limitation predates the single-result change and
is not fixed by it; mixed byte/permission regressions do not prove otherwise.
Linux-only tests do not establish macOS, remote engines, concurrency, full cold
onboarding or universal Cargo-project support. Continue from these limitations,
not from a claim that the developer-loop performance goal is achieved.
