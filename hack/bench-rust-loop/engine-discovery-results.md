# Matched discovery CLI A/B and candidate Rust validation

2026-09-11, Linux/amd64. Raw whole-process samples, including retained warmups,
are in [engine-discovery-exact-pairs.csv](engine-discovery-exact-pairs.csv).
The separate native/candidate validation is in
[engine-discovery-invalidation.csv](engine-discovery-invalidation.csv).

The discovery patch produces a measured **162.834 ms median paired whole-command saving** in 60 alternating standalone checks using the embedded image-managed driver with **cleanup=false**. All 60 candidate commands are faster. The measured list/start saving is 164.943 ms per pair at the median, while compilation and execution-cache states remain unchanged. This is a real CLI result, not a profiler what-if or an inferred subtraction result.

This is **not** the ordinary `cleanup=true` prefix-discovery result. That path must retain discovery of old managed engines and has separate, inventory-dependent performance. It is also not a faster-Cargo, cold-onboarding, invalidation A/B, artifact-export or cross-platform result.

## Inputs and boundaries

- Matched run: `/tmp/dagger-rust-cli-pair-do0cpcib`; 60 timed pairs, one retained/excluded warmup pair. Ordinary new CLI process/session each time; no listen/resident cache.
- Before CLI: `/tmp/dagger-rust-discovery-cli-before`, SHA256 `07ac78cb3e8fd772e0d3f81835f00cb88c65b03d9a8bbfbfe45291bf37b7256c`.
- After CLI: `/tmp/dagger-rust-discovery-cli-after`, SHA256 `c26fe1b468dfbb1d37e4e92b2abc6578c33896bcee004a54ada0c1821b243d2e`.
- Both binaries were built with Go 1.26.6. Both use the same prepared workspace `/tmp/dagger-rust-loop-714debkv/dagger`, same local module and unchanged engine. No engine changes are compared.
- Rechecked engine container `4fdc432dd5e5ea7511d4488a547dc09154a7e810c7266fc81825fcad0df18ae8`, image `sha256:7c0520ee656a91e994b61388342f23de299693d065a8b6f5607db6743b3389c2`; upstream base `1ea6197c436636bab81cc62607e3606d860671a2`, source `3e9c238f20ef93625e30a4727f2521cbd647b456` plus the discovery patch for the after CLI.
- Both sides have no `DAGGER_ENGINE` override and use the same embedded Docker-image selector, custom container name `dagger-engine.rust-main-1ea6197c43`, with `cleanup=false`. DNT=1, isolated CLI state, localhost OTel enabled; native recorder disabled for headline timings. These diagnostic settings are not a claim about every user's analytics configuration.
- Candidate validation: `/tmp/dagger-rust-loop-tjvqhj0_`, same candidate CLI and managed driver. First check uses already-prepared Rust/toolchain layers, fresh Cargo cache namespace; `cold_claim=false`.
- Raw OTel: `/tmp/dagger-rust-main-1ea6197c43-otel.jsonl`. No analysis, builds or tests competed with the timed pair window. This audit performs no engine calls.

## All 60 pairs

| Metric | Before median [min,max] ms | After median [min,max] ms |
|---|---:|---:|
| Whole CLI process | 658.500 [599.299,841.950] | 473.683 [440.975,597.357] |
| Whole CLI mean | 669.992 | 497.138 |
| Whole CLI p95, nearest rank | 795.784 | 575.472 |
| Docker list | 185.313 [176.397,258.119] | 19.285 [16.869,27.078] |
| Docker start | 11.067 [10.500,12.360] | 11.425 [9.846,13.681] |
| Connection envelope | 329.195 | 166.767 |
| Before CLI root | 28.075 | 28.042 |
| After CLI root | 11.504 | 10.045 |

- Median paired whole-process saving: **162.834 ms**; mean: **172.854 ms**; min–max **10.125–369.712 ms**. Faster: **60/60**.
- The difference of marginal process medians is **184.817 ms**, not the median paired saving.
- Median paired list saving: **165.341 ms**; list plus start: **164.943 ms**. Each side has one list and one start in every timed trace.
- Whole-process saving minus observed list/start saving: median **−1.105 ms**, mean **6.323 ms**, min–max **−154.784–214.537 ms**. This residual is attribution, not another performance claim.
- Correlation of per-pair whole-process saving with list saving is **−0.103**. The listing improvement is comparatively stable; unrelated lifecycle variation dominates the spread of individual savings. Do not turn the maximum pair into a headline.

Actual commands in every timed trace:

```text
before: docker ps -a --format {{.Names}}
after:  docker ps -a --format {{.Names}} --filter name=^/?dagger-engine\.rust-main-1ea6197c43$
both:   docker start dagger-engine.rust-main-1ea6197c43
```

The custom engine uses a dot after `dagger-engine`, not the standard hyphen prefix. The exact-name hint is appropriate because cleanup is disabled. This must not be generalized to a cleanup-enabled command that needs the old-engine set.

## Cache integrity and maintained wcprof gates

All **120 timed A/B traces** contain:

- Three `Container.withExec` recipe hits.
- **Zero actual `exec` operations and zero `exec.processRun` phases**.
- Twelve actual POST/query spans, 154 marked engine spans, and one matching 154-span completeness marker.

These are light raw checks across every pair. Six selected matched traces additionally pass the maintained wcprof full structural gate. Pair selection is independent of saving: nearest-to-both-medians pair **23**, pair containing before maximum **37**, and pair containing after maximum **1**. Both sides of each chronological pair are retained.

| Pair/side | Process ms | Before root ms | Root ms | After root ms |
|---|---:|---:|---:|---:|
| 23 before | 645.927 | 26.437 | 609.903 | 9.587 |
| 23 after | 475.128 | 28.680 | 436.784 | 9.664 |
| 37 before | 841.950 | 27.908 | 791.084 | 22.959 |
| 37 after | 472.238 | 27.738 | 434.677 | 9.824 |
| 1 before | 684.814 | 27.603 | 647.176 | 10.035 |
| 1 after | 597.357 | 26.837 | 560.477 | 10.043 |

All six gates: PASS, 172 operations, 154/154 engine spans, one root, no missing/open/orphaned spans, cycles, unresolved waits, malformed timing, dropped links, unschedulable operations or start conflicts. Replay drift is within 0.1%.

Representative wcprof attribution: list **186.0→18.9 ms self**; Rust check **56.6→54.3 ms self**; asModule **48.8→45.2 ms self**. Across all timed traces, supporting direct-child-subtracted medians are Rust **56.356→55.172 ms** and asModule **46.376→47.347 ms**. These supplementary wall metrics do not replace causal wcprof self-time and show no meaningful module-runtime optimization from this CLI patch.

Before maximum retains a 108.4 ms session-start interval and 68.1 ms trace-subscription interval. Candidate maximum also retains broad costs: Rust self 64.3 ms, asModule 54.6 ms, session start 51.1 ms and trace-consumer 48.8 ms. `consuming /v1/traces` measures subscription establishment, not exporter flushing or CPU.

## Separate candidate validation: real edits and dependency upgrade

The candidate completes all checks using the same embedded managed-image `cleanup=false` path. This is a correctness/current-state run, **not a matched before/after edit experiment**. Native means Cargo via `docker exec`, with the same pinned Rust image, source, `/src` working directory, target layout and `cargo check --workspace --locked` flags.

| Scenario | n | Native median ms | Candidate Dagger median ms | Median within-sample overhead ms |
|---|---:|---:|---:|---:|
| Exact | 5 | 132.288 | 547.827 | 409.021 |
| Application edit | 5 | 295.114 | 911.900 | 593.061 |
| Workspace-library edit | 5 | 448.385 | 1039.235 | 590.850 |
| External bstr 1.12→1.13 | 1 | 1654.587 | 2193.897 | 539.310 |
| Dependency followup | 1 | 144.188 | 464.343 | 320.155 |

The dependency transition runs Dagger first; both download/check bstr in independent Cargo caches. It is one observation, not a distribution. The five-sample exact median differs from the 60-pair result and is retained. Do not compare these sequential validation medians to the earlier direct-container run and attribute the differences to discovery.

Prepared-toolchain first check is **6817.658 ms native / 6890.819 ms Dagger**, an observed **73.161 ms** difference. Dagger's source-sync/Cargo execution is 6249.220 ms and both preparation execs hit. There is no Rust image/toolchain download/install cost to optimize in this trial: **this is not achievement of the first-install overhead goal**.

Correctness and rebuilding:

- Every one of the five app edits and five library edits contains one actual exec/process phase. The dependency upgrade does too; prepared-toolchain operations hit cache.
- Every app sample rebuilds only **ripgrep 15.2.0** on both sides.
- Every library sample checks **grep-printer 0.3.1, grep 0.4.1, ripgrep 15.2.0** on both sides.
- The external upgrade rebuilds the same ten packages on both sides: **bstr 1.13.0, globset 0.4.20, grep 0.4.1, grep-cli 0.1.12, grep-index 0.0.1, grep-printer 0.3.1, grep-regex 0.1.14, grep-searcher 0.1.17, ignore 0.4.33, ripgrep 15.2.0**. Unrelated memchr is not rebuilt.
- Native/Dagger Cargo.toml SHA256 both `8550b637f78a4f6042d66f0da57a12934dd5216e7f20046df4653df1ce761ad1`; Cargo.lock both `a96a6bf35ca3c4ddb640e6e66f2731abe853d508b034ec6a6ea54f52bc71b815`.
- Failure probe exits **101** with a real 289.742 ms execution; repair exits **0**; old failure revisit exits **101** with a real 283.841 ms execution; repaired revisit exits **0** and performs no execution. Notably the failure revisit has three withExec *recipe* hits but still executes underneath: recipe hits alone cannot prove no execution. The A/B claim separately checked actual execution phases.
- All sixteen outside-timer Cargo diagnostic requests perform zero execs. Their cached producer stderr matches native package tuples, while the measured edit traces independently prove actual execution.

Seven validation OTel captures additionally pass full maintained gates: prepared first check (236 ops, 218/218 spans); median application and library (194 ops, 176/176 each); dependency (195 ops, 177/177); profiled exact (172 ops, 154/154); profiled application and library-repair (194 ops, 176/176 each). All gates have zero losses/open/orphaned spans, wait errors, cycles, dropped links and scheduling conflicts; replay drift is within 0.1%. All remaining validation process captures have matching raw completeness counts, though their full structural gate was not rerun.

Selected ordinary execution phases, including both source sync and Cargo: app **363.261 ms**, library **524.506 ms**, dependency **1638.864 ms**. No shell subphase instrumentation separates rsync from Cargo here.

## Native recorder scope

Maintained native wcprof analyzed all three populated diagnostic dumps, separate from the headline timings:

| Dump / recorded process | Native ops | Roots | Native makespan ms | Full CLI process ms |
|---|---:|---:|---:|---:|
| exact / profile-exact | 693 | 12 | 316.3 | 672.544 |
| application / profile-application | 733 | 12 | 717.0 | 1013.060 |
| library-repair / profile-library-repair | 733 | 12 | 780.2 | 1032.833 |

All have zero dropped events/open operations and approximately zero replay drift. Multiple independent request roots omit CLI/transport lifecycle and cross-query ownership. Their makespans are **not end-to-end latency**. Native coarse `Rust.check` self includes work that the connected OTel model assigns to nested requests/execs: e.g. native exact self 183.1 ms versus OTel 57.8 ms for the same 183.3 ms Rust wall interval. Do not sum these different representations or use the native ranking to erase outside-recorder costs.

`before.wcprof` and `revisit.wcprof` are unprofiled drain intervals, not native coverage of failure/revisit commands. First check and timed dependency upgrade have native profiling disabled. OTel supplies their complete CLI coverage.

## Retained outputs

Everything is under `/tmp/dagger-rust-discovery-ab-analysis*`: `-summary.json`, `-pairs.csv`, `-pair-processes.csv`, `-validation-summary.json`, `-validation-processes.csv`; thirteen `-<label>-trace.jsonl`, `-boundaries.json`, `-gate.txt`, `-wcprof.txt` sets; three `-native-<scenario>.txt` reports; the owned `.py` orchestration script and this report.

The offline profiler audit made no engine calls. Remaining scope is explicit: validate cleanup-enabled discovery separately, preserve backend/context/name semantics, and continue measuring ordinary edits/cold image delivery. The patch does not alter Dagger action identities, source synchronization, Cargo compilation or session ownership.

## Implementation and compatibility boundary

Previously the image driver listed every container before locally selecting
the current engine and old managed engines. It did so even when cleanup was
disabled, although that path could only reuse its exact target name.

Pass escaped, anchored, OR-combined name-filter hints into the existing backend
listing operation. With cleanup enabled, keep the managed-name prefix plus
any custom target; with cleanup disabled, request only the exact target. Keep
the authoritative literal local predicate before deciding which container may
be started or removed. Apple container has no supported name-filter option and
retains its full-list fallback followed by that same local predicate.

No new cache, persistent session, asynchronous GC, Docker-inspect/ID alias,
transport pool, daemon API, or engine dependency is introduced. Existing
Docker context/environment handling, start/create races and synchronous
cleanup are unchanged. Fake argv tests cover Docker, Podman, nerdctl and
Finch; only Docker was exercised live. Apple behavior is fake-tested, not a
claim of native macOS performance.

Read-only Docker 29.4.1 checks confirmed exact set parity with full listing:
45 containers remained present before/after; exact target selected one, while
prefix plus custom target selected 20. Only counts and owned target identity
are reported. Existing containers were not deleted to create a favorable
inventory. The development engine name uses a dot, unlike the managed prefix.

The earlier separate 20-sample-per-cell list-only control found prefix/custom
filtering about 35ms faster, with or without local OTel settings. That is not
the 163ms exact-only whole-command gain. A full cleanup-enabled CLI benchmark
requires an isolated daemon: running it on this host would delete preserved
engines. Neither that measurement nor a universal fixed saving is claimed.

## Reproduction

Build both CLIs with identical Go 1.26.6, CGO_ENABLED=0, -buildvcs=false and
linker flags. Before uses source 3e9c238f20; after adds only the driver patch.
The engine need not change for this CLI-only experiment. The existing engine
was rebuilt from this stack on upstream 1ea6197c43 with the pinned repository
dev workflow (not an arbitrary installed CLI):

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call \
  dev --docker=unix:///var/run/docker.sock deploy \
  --name=dagger-engine.rust-main-1ea6197c43 \
  --image=localhost/dagger-engine.rust-main-1ea6197c43 \
  --platform=linux/amd64 --debug-endpoint=false \
  --output /tmp/dagger-rust-main-1ea6197c43-bin
```

Use an unused, explicitly owned deployment name for a new reproduction; never
replace an unrelated engine. Keep the same selected engine during each pair.
From each respective before/after checkout, changing only the output filename:

```sh
rust_discovery_ldflags='-s -w -X github.com/dagger/dagger/internal/cmd/dagger.RunnerHost=docker-image://localhost/dagger-engine.rust-main-1ea6197c43?container=dagger-engine.rust-main-1ea6197c43&volume=dagger-engine.rust-main-1ea6197c43&cleanup=false -X github.com/dagger/dagger/engine.Tag=3e9c238f20ef93625e30a4727f2521cbd647b456 -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCS=git -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSRevision=3e9c238f20ef93625e30a4727f2521cbd647b456 -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSModified=true'
GOCACHE=/tmp/dagger-rust-go-cache CGO_ENABLED=0 go build -buildvcs=false \
  -ldflags "$rust_discovery_ldflags" \
  -o /tmp/dagger-rust-discovery-cli-after ./cmd/dagger
```

Start a local OTel receiver using the telemetry-capture skill. Both runs used
the retained `/tmp/dagger-rust-main-1ea6197c43-env.sh` wrapper: it removes
engine/session overrides, cloud credentials/config and OTLP headers; sets
DO_NOT_TRACK=1; isolates XDG config/data/state; points traces/logs/metrics at
127.0.0.1:43187 and enables live trace export. The engine comes from the
identical embedded selector, not an explicit-container bypass. These are
recorded diagnostic environment choices, not default-analytics coverage.

```sh
sh /tmp/dagger-rust-main-1ea6197c43-env.sh \
  python3 hack/bench-rust-loop/compare-cli.py \
  --before /tmp/dagger-rust-discovery-cli-before \
  --after /tmp/dagger-rust-discovery-cli-after \
  --workdir /tmp/dagger-rust-loop-714debkv/dagger --samples 60 \
  -- check rust:check

sh /tmp/dagger-rust-main-1ea6197c43-env.sh \
  python3 hack/bench-rust-loop/run.py \
  --dagger /tmp/dagger-rust-discovery-cli-after \
  --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
  --debug-url http://172.17.0.22:6060 \
  --ripgrep /tmp/dagger-rust-ripgrep-reference --samples 5 \
  --pinned-source-sync \
  --project-toolchain hack/bench-rust-loop/fixtures/rust-toolchain-rustfmt.toml \
  --prepare-project-toolchain --dependency-upgrade --dependency-first dagger
```

The prepared pair workspace was created by the same run.py fixture/settings;
use your own generated path. Resolve the owned engine's actual debug address
instead of assuming the historical IP. Keep the pinned ripgrep revision from
the harness. No competing builds, tests or analyzers ran during either timing
window. Afterward, engine ID/image were unchanged and the validation's native
container was verified removed; its source copies, logs and cache records remain.

Focused fake-only tests, then the same selection with the race detector, pass:

```sh
env -u DRIVER_TEST GOCACHE=/tmp/dagger-rust-go-cache go test -race -count=1 \
  -run='^Test(CollectEngines|DockerContainerLs|AppleContainerLs|ContainerLsFailure|ImageDriverCreateDiscovery|GarbageCollectEnginePreservesNames|ImageDriverCreateEnablesLoopbackDebugListener)$' \
  ./engine/client/drivers
git diff --check
```

Race package time: 1.043s. Tests cover literal regex escaping, OR hints and
deduplication, exact-only and cleanup-enabled selection, overbroad fallback
results, create/reuse/removal/preserved names, list failures and cancellation.
No broad DRIVER_TEST backend suite was run because it removes unrelated test
images/containers. Live read-only set parity supplements but does not replace
native backend compatibility tests.
