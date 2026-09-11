# Cache project toolchain preparation separately, 2026-09-10

## Result and scope

The module was reinstalling a configured Rust component after every novel source
edit. Preparing the toolchain from only the root toolchain files preserves that
work in an ordinary immutable Dagger container result. Full source still enters
the locked source reconciliation + Cargo action; no cache identity, session,
Cargo flag, compiler version or engine API is changed.

This is an **opt-in candidate in the diagnostic module**, not the finished
official Rust module or an across-the-board speedup. Edited-source runs improve,
but exact hits get slower and configured warm runs expose a serious teardown
tail. Keep those regressions visible before selecting a production default.

## Current upstream and runtime identity

The complete 01–12 stack was rebased onto upstream
`731bea2d61026bc6dfc029bd0803d7b4995cb71d` (workspace-config preservation).
`git range-diff` reports all 13 existing commits unchanged. The previous tip is
retained as `archive-rust-perf-before-731bea2d6`, pointing to `a2055a0a66`.
The rebased parent of this experiment is `afcf87671d9f3b28fb1653763879876182efe3cd`.

Rebuilt with the repository's pinned development workflow:

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call \
  dev --docker=unix:///var/run/docker.sock deploy \
  --name=dagger-engine.rust-main-731bea2d \
  --image=localhost/dagger-engine.rust-main-731bea2d \
  --platform=linux/amd64 --debug-endpoint=false --output ./bin
```

The existing normal engines were preserved. The dev loader replaced only its
deliberately created stopped placeholder. Build log:
`/tmp/dagger-rust-main-731-build.log`. Runtime identity:

- Engine image: `sha256:002684688952b4ce87736c29effecdb97f2d5e530f9df88833b7c3dba03d70b8`.
- CLI SHA256: `315466126e450f25806d61b8ae2a58b9c53e60337c200594812334f4eb8df34f`.
- CLI reports beta.12, commit `afcf8767`, dirty development build; module changes
  are interpreted from source and do not require another engine rebuild.
- Rust image: `rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b`.
- rustc 1.97.1, rustup 1.29.0, linux/amd64; pinned rsync packaging enabled on both
  module variants. No linker, profile or debug-info changes.

## Method and reproduction

Use pinned ripgrep `3fce3b5bb0236da2df6d99672afb8a719642eca7`, with the committed
root toolchain fixture added identically to both copies. It requests rustfmt
while retaining the image's compiler version. Native is Cargo through
`docker exec`, not raw host Cargo. Both sides run
`cargo check --workspace --locked`. Component installation is inside the first
check, and native naturally retains installed components across later commands.

Use an isolated CLI XDG state directory, unset cloud tokens/config and OTLP
headers, set `DO_NOT_TRACK=1`, and capture OTel locally as in the telemetry skill.
These measurements used port 43183 and the rebuilt engine's debug endpoint at
`http://172.17.0.29:6060` (resolve its current IP when reproducing):

```sh
export DAGGER_ENGINE=container://dagger-engine.rust-main-731bea2d
export DO_NOT_TRACK=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:43183
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:43183/v1/traces
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:43183/v1/logs
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:43183/v1/metrics
export OTEL_EXPORTER_OTLP_TRACES_LIVE=1

python3 hack/bench-rust-loop/run.py --dagger ./bin/dagger \
  --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
  --samples 5 --debug-url http://172.17.0.29:6060 --pinned-source-sync \
  --project-toolchain hack/bench-rust-loop/fixtures/rust-toolchain-rustfmt.toml \
  --ripgrep /tmp/dagger-rust-ripgrep-reference --dependency-upgrade \
  --prepare-project-toolchain
```

Omit `--prepare-project-toolchain` for the baseline. Each invocation gets new
source/target/registry/git cache keys; the engine, CLI state, images, network
and OS caches are shared. This is **not empty-engine or complete onboarding**.
No build/test process overlapped the timed trials. Local OTel was enabled;
native wcprof repair/application/exact captures are separate diagnostic calls,
not the unprofiled timing rows.

Batch order was baseline(3), pilot candidate(3), final candidate(5), baseline(5).
Native/Dagger order alternates inside each edit scenario; dependency first-side
was native, Dagger, native, Dagger respectively. These are sequential batches,
not sample-by-sample randomized module A/B measurements. Native times vary too.
Do not attribute every wall-clock delta to this change.

The pilot also passed `--no-update`; review found that rustup's no-explicit-name
installation path does not use that flag. It was removed before the final
five-sample runs, avoiding an unnecessary older-rustup CLI restriction. The
no-name path ensures the active toolchain and configured components/targets.
See the [rustup 1.29.0 command implementation](https://raw.githubusercontent.com/rust-lang/rustup/1.29.0/src/cli/rustup_mode.rs)
and [configuration implementation](https://raw.githubusercontent.com/rust-lang/rustup/1.29.0/src/config.rs).
The component-inspection accessor was added afterward for correctness testing;
the measured check implementation is unchanged. Warm pairs use that final API.

## Edited-source observations

Final runs; milliseconds, median [min, max], five samples except the one-time
dependency upgrade in each run:

| Scenario | Native baseline batch | Dagger baseline | Native candidate batch | Dagger candidate |
| --- | ---: | ---: | ---: | ---: |
| Exact | 129 [125,151] | 438 [404,452] | 137 [135,207] | 510 [444,821] |
| Application edit | 299 [297,308] | 1448 [1323,1534] | 432 [309,557] | 1089 [780,1483] |
| Workspace-library edit | 540 [465,823] | 1819 [1566,2193] | 486 [473,639] | 1155 [1092,1407] |
| External bstr upgrade (n=1) | 1774 | 3069 | 1631 | 2209 |

Median *paired* Dagger-minus-native overhead in the final batches:
application 1140 → 590ms; workspace-library 1233 → 638ms. The single external
upgrade pair was 1295 → 578ms overhead. This approaches the target on this
fixture's edit path; it does not establish universal performance or cold success.

The three-sample pilot's Dagger application/library medians were
1585/1950 → 820/932ms. Its candidate application maximum was **6551ms**, retained
in the raw results and investigated below. Never report just that pilot median.

Every novel baseline application/library/dependency execution log redownloaded
rustfmt: 7/7 pilot and 11/11 final. Neither candidate's corresponding Cargo
execution logs contained a component download. Exact-hit diagnostic logs are
excluded from this count: they describe the cached producer, not a new install.

Both variants rebuilt the same ten packages for bstr 1.12.0 → 1.13.0, retained
unrelated memchr, and left locked inputs unchanged. All four batches passed
compile failure, repair, old-failure revisit and repair-revisit checks.

First checks with empty Cargo caches, but an existing engine/image:
baseline pilot 6.846s native / 7.449s Dagger; candidate pilot 7.492s / 7.444s;
final candidate 9.948s / 11.298s; final baseline 6.756s / 7.383s. These variable
single trials are not evidence of better onboarding. wcprof shows 856ms in the
final candidate's toolchain-setup execution envelope, plus 9.25s in its Cargo
envelope; the baseline combines setup/Cargo in a 6.85s envelope. Runtime and
network variance are material; no cold-gain claim is made.

Raw samples: [invalidation CSV](project-toolchain-invalidation.csv). Local full
runs, in order: `/tmp/dagger-rust-loop-4cuyfekq`, `2jpemz_c`, `kk7kixl4`,
`5p1l69np` (the latter three have the same `/tmp/dagger-rust-loop-` prefix).

## Exact-hit regression and teardown outliers

Thirty alternating pairs per case, same CLI/engine, separate prepared workspaces,
one retained but excluded warmup pair. Run `compare-cli.py --before ./bin/dagger
--after ./bin/dagger --before-workdir BEFORE --after-workdir AFTER --samples 30
-- check rust:check`.

| Case | Baseline median [min,max] ms | Candidate median [min,max] ms | Median paired candidate cost |
| --- | ---: | ---: | ---: |
| No toolchain file, two-crate fixture | 448 [383,577] | 467 [404,537] | +5.23ms |
| Configured ripgrep | 438 [405,579] | 473 [418,6330] | +32.54ms |

Configured candidate samples 10,18,28 took 6197,6299,6330ms: **three of thirty**,
versus none in the matched baseline. Their complete traces contain no Cargo
execution and attribute 5.82–5.93s of opaque self-time to `Rust.check`. This is a
user-visible regression; median-only reporting would hide it. The candidate
stays opt-in while the lifecycle issue is investigated.

The earlier 6551ms application outlier is more precisely localized: shell work
ended at +718.587ms, the final nested query at +733.168ms, and `Rust.check` at
+6478.292ms. Matching engine logs show its post-evaluation telemetry flush took
2.234ms. The remaining ~5.74s is after both Cargo and flushing, not recompilation.

Code inspection points to `core/sdk/dang/shared/shared.go`: a short-lived local
HTTP server uses a process-global default client, then graceful shutdown without
an owned client-pool cleanup. Go's shutdown can wait over five seconds for an
accepted connection that never sent a request. This is a concrete lifecycle
hypothesis, **not yet a connection-state diagnosis or an implemented engine fix**.
Next: verify connection states and scope a transport to the invocation; retain
graceful draining and never close the process-global pool.

Follow-up: the [nested-client lifecycle investigation](nested-client-lifecycle-results.md)
confirms the actual shutdown wait, adds owned-pool cleanup and regression tests,
and records an uninstrumented comparison. This section preserves the original
experiment's evidence and limitations.

Raw [warm pairs](project-toolchain-warm-pairs.csv); local runs
`/tmp/dagger-rust-cli-pair-t4dw7n0f` and `/tmp/dagger-rust-cli-pair-_onxt2zs`.
No-file fixture setup/regression runs: `/tmp/dagger-rust-loop-jki90z74` (before)
and `/tmp/dagger-rust-loop-zh3sok3a` (after). Their single-row timings are only
diagnostic; the latter also includes this engine's first image materialization.

## Profiler and correctness gates

Maintained wcprof analyzed fourteen complete final-batch OTel captures: initial,
application, library, dependency, profiled repair/application, and exact per side.
All structural gates pass: one root, no missing/open spans, unresolved waits,
or dropped links. Replay drift is -0.0% to -0.1%, except baseline exact at -2.4%.
The pilot outlier and all three warm outliers also pass their complete capture
gates. Outlier replay drift rounds to -0.0%.

One matched application sample's runtime envelope falls from 1044ms to 354ms;
the candidate does not re-execute toolchain installation. These are measured
envelopes including runtime work, not compiler-only time or what-if savings.
Six native dumps have 614–698 operations, 10–12 roots, no open/dropped events
and drift rounding to -0.0%. Native cross-session causality remains partial;
use complete OTel plus process boundaries for the end-to-end interpretation.

Captures, gate stderr, reports and boundaries are under
`/tmp/dagger-rust-toolchain-final-*`,
`/tmp/dagger-rust-toolchain-stage-after-outlier-*`, and
`/tmp/dagger-rust-toolchain-warm-outlier-{10,18,28}-*`.
Raw telemetry is `/tmp/dagger-rust-toolchain-stage-otel.jsonl`; no private
analyzer source or raw session telemetry is committed.

Post-rebase verification: workspace unit package passes (0.033s); HTTPState
race tests pass (1.161s, eight top-level tests). The initial sandbox listener
failure was rerun unchanged with localhost permission, not fixed in code.
`test-toolchain.py` passes eleven standalone checks and six direct component
manifest reads: component addition, bad config/repair, deletion, legacy-file
precedence, source failure/repair. Evidence:
`/tmp/dagger-rust-toolchain-test-8h6_s1yh`. Two earlier harness failures remain
recorded (`1mcb2kg3`: missing Git root; `2wrtj195`: manifest target suffix parser);
neither is counted as a successful test. Only test-owned files are deleted
during deletion cases, with prior contents preserved in input records.

Still unvalidated: other rustup versions, a different compiler download,
additional targets, nested/ancestor or symlinked toolchain files, custom
toolchain paths, explicit overrides, moving channels, macOS/remote execution,
artifact export and the complete installation journey. This change neither
claims Bazel-equivalent crate caching nor solves the remaining engine tax.
