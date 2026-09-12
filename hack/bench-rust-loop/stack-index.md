# Rust developer-loop performance stack

This is the retrospective index for **20 stacked branches / 22 commits** through
`f1d6824edb7fe55deaf14e0a8117bfa465c98142`, rebased onto upstream
`ff626243dca48bad2ff5c18e2f2b401f58f3c83d`. It is not a claim that this is still
the latest upstream revision. The index itself is a subsequent documentation
change, not one of those 22 commits.

Before publishing this index, a live upstream check found `main` had advanced to
`9b8500afe875c42afc6780b9e15a7c9a5b294490`: only the Go SDK library pin changed
since `ff626243`, with no overlapping stack files. Rebasing and validating that
new base is still pending at this snapshot; none of the measurements below used
that new revision.

A later [9b235855 source checkpoint](#rebase-checkpoint-9b235855) maps all 21
branches, including this index, after rebase. It does not relabel the historical
measurements below as new-runtime results.

The goal remains an official, broadly useful Rust module with ordinary standalone
checks and generation/builds: faster reusable results than native Cargo, ideally
only tens of milliseconds of Dagger overhead on real invalidation, and roughly
0.5–1 second extra for first use. Final artifact transfer counts. **The full goal
is not achieved.** These fixtures are not the official module, all Rust projects,
or a Bazel comparison.

## How to read and reproduce the record

- Each branch contains the preceding branches. Branches 01 and 14 each add two
  commits; every other numbered branch below adds one. This is not 20 independent
  implementations or 20 demonstrated speedups.
- The first six commit bodies are empty. Their explanations below are a
  retrospective index of tracked source, README and report evidence; no history
  has been rewritten and no original commit is presented as better documented
  than it was.
- The linked tracked reports are the reproduction/evidence entry points. They
  identify fixtures, flags, build/toolchain hashes, controls, sample counts,
  validation and limitations. Start with the [check-loop instructions](README.md)
  or [generator instructions](../bench-rust-generators/README.md), build the
  specified variants, and replace local example paths with your own outputs.
  Old `/tmp` paths identify original evidence, not dependencies promised to exist
  on another machine. Some early reports lack a complete one-command A/B recipe;
  preserve that limitation rather than inventing one.
- Historical measured hashes must stay historical. Rebasing changes commit IDs,
  not old binaries or their measurements. The fd9-based generator cohort is
  retained at tag `archive/rust-stack-fd9bc0036a-04e77e6b`, pointing to
  `04e77e6b417a85e1db7472a5752ffd689d665f12`. Earlier checkpoints use the
  `archive-rust-perf-before-*` tags recorded in individual reports. The original,
  broader experiment is separate at `archive/rust-performance-before-rebase`
  (`7adcdbee173df15473c1613f36ff1312c5d64fd9`), not the implementation to promote.
- **Do not add savings across rows.** Controls, upstream revisions, engine
  histories, instrumentation and workloads differ. A paired median difference
  is not a difference of independent medians. Diagnostic phase savings are not
  automatically whole-process savings.
- Most native controls are Cargo via `docker exec`, not host-native Cargo.
  Exact hits, novel app edits, workspace-library edits, external dependency
  upgrades and first use are different scenarios. Engine-cache cold excludes
  several already-installed tools/images; it is not a clean-machine installation.
  Local OTel and analytics opt-outs are recorded conditions, not default-cloud UX.
- Retain failed correctness runs, regressions, outliers and rejected wcprof
  gates. Incomplete profiles can retain process timings but cannot prove absence
  of hidden work. Raw telemetry/binaries and private analyzer implementation are
  not published here; tracked CSVs and audit summaries are the durable evidence.

Inspect the indexed history without changing refs:

```sh
git log --reverse --format=fuller ff626243..f1d6824
git show COMMIT
```

## Branch inventory

Tips are anchored to the indexed revision above; future rebases need a new
mapping, not silent relabeling of measured binaries.

| Branch | Tip | Change(s) added by this branch |
| --- | --- | --- |
| `perf/rust-01-ordinary-check-benchmark` | `79ea16d2aa` | `c6b5d2c6d3`, `79ea16d2aa` |
| `perf/rust-02-invalidation-investigation` | `0f5fc785eb` | Source freshness reconciliation |
| `perf/rust-03-lazy-oauth-startup` | `ae5c07fa0b` | Lazy credential refresh |
| `perf/rust-04-ripgrep-invalidation` | `e817ace7cf` | Real-project edit coverage |
| `perf/rust-05-disposable-cold-loop` | `efb909b84a` | Owned empty-engine trials |
| `perf/rust-06-cold-readiness` | `58d3084c5e` | Transport readiness wait |
| `perf/rust-07-slim-toolchain-evaluation` | `86a3da4c65` | Optional image evaluation |
| `perf/rust-08-external-dependency-upgrade` | `6878684266` | Real library-version upgrade |
| `perf/rust-09-source-sync-profiling` | `83edeb3e5c` | Correct phase attribution |
| `perf/rust-10-cli-startup-width-tables` | `8f6771ecc8` | Upstream Unicode-width update |
| `perf/rust-11-pinned-source-sync-tool` | `e6f7200e14` | Optional rsync packaging |
| `perf/rust-12-verified-http-input-reuse` | `daa185773d` | Retained checksum-pinned inputs |
| `perf/rust-13-project-toolchain-layer` | `7179fef23f` | Optional immutable toolchain setup |
| `perf/rust-14-nested-client-transport-lifecycle` | `d3e1c431f7` | `1f096f5ba1` lifecycle fix; `d3e1c431f7` revalidation |
| `perf/rust-15-stored-toolchain-evaluation` | `80833e16f7` | Private-field experiment; getter remains default |
| `perf/rust-16-filtered-engine-discovery` | `d31dd491ba` | Backend name-filter hints |
| `perf/rust-17-single-generator-snapshots` | `132fe82493` | Preserve one generator's immutable snapshots |
| `perf/rust-18-generator-benchmark` | `4387a28398` | Generator fixture, guards and full evidence |
| `perf/rust-19-auto-apply-paths` | `32fcabf43c` | Skip unused explicit-apply preview |
| `perf/rust-20-cli-comparison-evidence` | `f1d6824edb` | Same-engine CLI harness and retained regressions |

## Rebase checkpoint: 9b235855

This source checkpoint includes **21 branches / 23 commits**, including the
index introduced by `26040b59aa`. The frozen upstream target is
`9b235855b35bf4508b1a5ddf64a5f36b6033a188`; the rebased stack checkpoint is
`bfb0c200efd6395656bc831da0b810d5027f289b`. These are explicit snapshots, not
a promise that upstream or branch tips have stopped advancing.

The prior complete stack is retained at tag
`archive/rust-stack-ff626243-26040b59`, pointing to
`26040b59aa4a6ea32b6d91a725164feb7b735f55`. The older fd9 archive tag and the
historical table above remain unchanged. The archive was published separately;
remote stack-ref publication is a distinct step from the local mapping below.
Old measured commits remain addressable and the archive must not be rewritten.

| Branch | Historical ff626 tip | Rebased 9b235855 tip |
| --- | --- | --- |
| `perf/rust-01-ordinary-check-benchmark` | `79ea16d2aa` | `2456864793` |
| `perf/rust-02-invalidation-investigation` | `0f5fc785eb` | `91e80665ea` |
| `perf/rust-03-lazy-oauth-startup` | `ae5c07fa0b` | `889f6edb4e` |
| `perf/rust-04-ripgrep-invalidation` | `e817ace7cf` | `012902ecfd` |
| `perf/rust-05-disposable-cold-loop` | `efb909b84a` | `1d210e8c9c` |
| `perf/rust-06-cold-readiness` | `58d3084c5e` | `d9cb6c2bf7` |
| `perf/rust-07-slim-toolchain-evaluation` | `86a3da4c65` | `f649e3b4c8` |
| `perf/rust-08-external-dependency-upgrade` | `6878684266` | `85afe07032` |
| `perf/rust-09-source-sync-profiling` | `83edeb3e5c` | `729429078f` |
| `perf/rust-10-cli-startup-width-tables` | `8f6771ecc8` | `c4e398d787` |
| `perf/rust-11-pinned-source-sync-tool` | `e6f7200e14` | `334b646a81` |
| `perf/rust-12-verified-http-input-reuse` | `daa185773d` | `dc2f9826aa` |
| `perf/rust-13-project-toolchain-layer` | `7179fef23f` | `0ab528840c` |
| `perf/rust-14-nested-client-transport-lifecycle` | `d3e1c431f7` | `2a7464a859` |
| `perf/rust-15-stored-toolchain-evaluation` | `80833e16f7` | `2f097d0e84` |
| `perf/rust-16-filtered-engine-discovery` | `d31dd491ba` | `d3dd86713c` |
| `perf/rust-17-single-generator-snapshots` | `132fe82493` | `116ded2d7c` |
| `perf/rust-18-generator-benchmark` | `4387a28398` | `4175bfb58a` |
| `perf/rust-19-auto-apply-paths` | `32fcabf43c` | `36b6ea0359` |
| `perf/rust-20-cli-comparison-evidence` | `f1d6824edb` | `533dffbc52` |
| `perf/rust-21-stack-index` | `26040b59aa` | `bfb0c200ef` |

The additional non-tip commits map as follows: initial fixture
`c6b5d2c6d3` → `28311bf0e4`; nested-pool fix
`1f096f5ba1` → `2377809de9`. Branches 01 and 14 still contain two commits each.
The table anchors branch tips before any subsequent documentation supplement.

### Upstream changes and relevance

From ff626 to this target, four upstream commits (two changes plus their merges)
touch five files, with 119 insertions and two deletions. There is **no file
overlap** with this 23-commit stack:

- `30918c5d7c` / merge `9b8500afe8` (PR #14128) updates the
  [Go SDK library pin](../../core/sdk/go_sdk.go) from the v0.21.9 commit to the
  v1.0.0-beta.12 commit. Go module generation passes this through `--lib-version`,
  so its normal codegen/download/build work can change. The external Go SDK's
  own source delta is not audited by comparing this repository alone.
- `26a952eafb` / merge `9b235855b3` (PR #14129) changes the
  [migration planner](../../core/schema/workspace_migrate_modules.go) to reuse
  installed named SDK providers and pins for unversioned runtimes before registry
  resolution. It preserves explicit-version and scope-ownership conflict errors.
  Added [planner cases](../../core/schema/workspace_migrate_modules_test.go),
  [CLI migration coverage](../../core/integration/workspace_migration_sdk_test.go)
  and a [changelog entry](../../.changes/unreleased/Fixed-20260911-224150.yaml)
  cover native/legacy configs and preview/apply/repeat behavior.

There are no upstream Dang/parser, egraph/cache, client/session lifecycle,
telemetry, dependency-manifest, benchmark or dev-build recipe edits in this delta.
That supports a small revalidation scope; it is not proof of unchanged runtime
performance or a reason to time an old engine as the new source.

### Source validation and runtime status

Independent read-only comparison confirms all 23 patch diffs and commit-message
bytes match, all 21 local branch tips match the mapping, and the final tree delta
is exactly the upstream delta. All 23 rebased commit objects contain SSH signature
headers; header presence is not a separate signature-trust verification. The
three original untracked archive files remain byte-identical. Recorded detached
experimental worktree HEADs are unchanged; their uncommitted source contents
are outside this mapping audit. A new detached engine-source worktree is separate.

Portable source checks, before adding later changes:

```sh
git range-diff ff626243..26040b59aa 9b235855..bfb0c200ef
git rev-list --count 9b235855..bfb0c200ef
git diff --stat 26040b59aa bfb0c200ef
git rev-parse 'refs/tags/archive/rust-stack-ff626243-26040b59^{commit}'
```

Focused migration planner unit tests pass (0.031s package time); the supported
dev deployment also completed from clean `bfb0c200ef` source. The new engine image
is `sha256:8683dc8fbb0f3585afe8e2adeb09738971a462b17f922ef4ac86d75fe64c9004`,
container `3c9df20b781ee4b1cf5b360b20b55030d04731b85bf575042f6a1538535affb8`.
Its exported CLI SHA256 is
`ff5acf117d2fdab17dbbd0581178843c01f0a6c962736322814b5d0b7a00c576`.
The dev CLI reports `unknown` commit; revision provenance comes from the verified
clean source input, not embedded VCS metadata. The owned never-started deployment
placeholder was replaced; older engines and their caches were preserved.

The focused integration selection below completed successfully with 20 reported
passing cases (2m20s workflow). Its progress summary reported 41.2% dropped
telemetry: this is a test result, **not** a certified wcprof performance capture.
The separate ordinary Rust correctness/performance cohort is still pending on
this rebuilt base. Validation commands/selectors are:

- Planner unit selector `^TestModuleMigration(UsesInstalledSDK|Graph|ConflictsPreserveFiles)$`
  in `./core/schema`.
- Integration selectors `^TestGo$/^(TestUseDaggerTypesDirect|TestUtilsPkg|TestWithOtherModuleTypes)$`,
  `^TestWorkspaceMigration$/^TestWorkspaceMigrateInstalledSDK$`, and
  `^TestModule$/^TestBuiltinDangDependencyModules$/^go_child$` in `./core/integration`,
  using the supported `api call engine-dev test` workflow and rebuilt source.
  The completed command combined the three suite/function selectors and skipped
  the other four child-module cases; it used `--parallel 1 --timeout 10m
  --test-verbose`. No broad package sweep was run.
- A separate ordinary Rust edit/failure-repair/generate correctness pilot, with
  normal cache identity, final artifacts and complete-profile gates retained.
  This remains a required next check, not a result supplied by this document.

No new timing win is established by this rebase. Existing n=30 measurements and
the local Dang phase pilot remain attached to their original source, binaries,
instrumentation and cache histories. Append actual new validation results rather
than changing those historical identities.

## Decisions, reproduction and observed impact

### 01 — Establish the ordinary standalone check baseline

`c6b5d2c6d3` adds the two-crate fixture and full-process native/Dagger loop.
`79ea16d2aa` captures individual check paths and records a repeated invalid
source returning success. This exposed a correctness problem before any speed
claim was acceptable. Neither commit has a body; the
[README's initial failure investigation](README.md#current-main-validation-2026-09-10)
retains the repro, engine baseline and failed result. This branch establishes
measurement and a false-green regression, not an optimized module.

### 02 — Make source changes visible to Cargo freshness checks

Immutable source timestamps can be older than fingerprints in a reused mutable
Cargo target. Add checksum-based rsync into a new source cache using the existing
LOCKED cache-mount API, without preserving old source mtimes, then run Cargo
under the same locks.
Changed/deleted files reconcile; unchanged files retain freshness. The
[tracked investigation and seven-sample baseline](README.md#current-main-validation-2026-09-10)
explain the native old-mtime repro and failure/repair/old-failure revisit.
This fixes the fixture's invalidation hazard; it does not establish a speedup.
Rsync provisioning remains included in first use. Commit body is empty.

### 03 — Avoid unrelated OAuth work on every CLI command

Defer refresh until the existing environment-secret resolver requests the
credential. Unrelated `version`/`check` commands previously contacted a provider
with expired credentials. [Report and raw CSV](oauth-startup-results.md) record
nine alternating samples per variant: check medians 1096.67 → 891.11 ms
(difference of medians, not a paired statistic). Tests cover deferred requests,
real resolution and explicit-token preservation. The gain depends on credential
state/network; broad auth integration and a complete A/B command are not supplied
by that early report. Commit body is empty.

### 04 — Test real ripgrep edits and persistent dependencies

Add pinned ripgrep, observable application/library edits and persistent
registry/Git caches so the native reference is not unfairly warmer. The
[report](ripgrep-check-results.md) and [run instructions](README.md) retain exact
inputs, ten matching rebuilt-package sets and failure/repair/revisit checks.
Five-sample Dagger medians remain 851.97 ms exact, 1191.76 ms app and 1534.76 ms
library. This is truthful coverage, not an improvement claim; version upgrades,
artifacts and cold install were not measured. Commit body is empty.

### 05 — Add an owned reset and first-use workflow

Create a fresh engine volume and CLI state per trial; remove only the resources
that trial owns. The [reset instructions](README.md#reset--first-use-loop) and
[first-use report](first-use-results.md) preserve the initially failed drain and
the corrected diagnostic trial: provisioning plus first check 34.62 seconds,
native first check 5.65 seconds. Image delivery dominates; Docker, CLI, engine
image and native Rust image were already installed. This establishes the gap,
not complete onboarding or a cold win. Commit body is empty.

### 06 — Wait for transport readiness instead of fail-fast polling

Scope `WaitForReady` to the readiness Info probe; preserve server-unavailable
retries and cancellation. [Repro and regression cases](cold-readiness-results.md)
show client creation 2044.59 → 1092.95 ms in one diagnostic pair, but the full
cold command regresses amid download/setup variation. This is a localized
readiness result, not an overall first-use speedup or a distribution.

### 07 — Evaluate a smaller official toolchain image

Use the existing image option, retaining Cargo/compiler behavior. The
[pinned-image repro](slim-toolchain-results.md) records 566.46 → 316.87 MB
compressed layers and unpack observations around 10.3–10.7 → 4.6–4.8 seconds.
Two sequential cold trials are not a causal full-flow A/B. Correctness and gates
pass, but missing native packages/check components and platform coverage keep
this an image evaluation, not a universal default.

### 08 — Change an application's actual Rust library dependency

Prime bstr 1.12.0, upgrade manifests/lockfile to 1.13.0 once per isolated cache
namespace, and verify ten matching rebuilt packages plus unrelated memchr reuse.
[Exact repro and complete gates](external-dependency-upgrade-results.md) retain
two first-upgrade native/Dagger pairs with 643/610 ms overhead. This covers a
dependency-version change rather than only workspace-source invalidation;
it is not a compilation speedup or multiple-repository result.

### 09 — Separate source reconciliation from the runtime envelope

Optional shell probes bracket rsync and Cargo without splitting their locked
action. [Repro and phase evidence](source-sync-phase-results.md) find about
56 ms source sync and about 79–82 ms additional runtime envelope in the diagnostic
upgrade runs. Prior subtraction had over-attributed that envelope to rsync.
No production optimization is made; probes add overhead, and differently
provisioned runs are not an A/B performance result.

### 10 — Remove eager Unicode-width table startup

Adopt upstream go-runewidth v0.0.30 rather than a custom cache. The
[matched-build repro/tests](cli-startup-width-results.md) include Unicode,
concurrency and TUI checks. Sixty version pairs save 23.97 ms paired median;
30 ordinary exact-check pairs save 25.61 ms paired median. Whole-check variance
and the final regressing pair remain. This is pre-root CLI work on Linux, not
faster Cargo, cold installation or comprehensive terminal/platform coverage.

### 11 — Deliver pinned rsync packages without runtime APT resolution

Opt into verified Debian package Files plus ordinary dpkg while retaining the
same reconciler. [Repro, package trust boundary and all timings](source-sync-delivery-results.md)
show roughly 2.5 seconds less install setup after allowing for small downloads.
Four cold trials have substantial image/network variation; do not credit all
their whole-flow difference. Thirty exact-check pairs regress by 15.16 ms paired
median. Pinned bookworm/amd64 only; remains opt-in, not the module default.

### 12 — Reuse owned, retained checksum-verified HTTP content

Avoid revalidation only when the canonical snapshot exists and its digest
matches a nonempty checksum. [Contract, repro and tests](verified-http-input-reuse-results.md)
cover restart, offline reuse, cancellation and changed/unpinned inputs. The
controlled 30-pair exact comparison saves 7.94 ms paired median; the earlier
unequal-history batch regresses. This intentionally pins the retained
representation across origin changes/outages/expiry; maintainers must approve
that semantic choice. No empty-cache or substantial Rust speedup is established.

### 13 — Cache project toolchain preparation independently of source

Filter root toolchain configuration into ordinary immutable setup, then reconcile
full source under existing Cargo locks. [Repro and component-manifest tests](project-toolchain-results.md)
prove baseline novel edits redownload rustfmt while the candidate reuses it.
Sequential n=5 app/library batches improve, but are not randomized module A/Bs;
30-pair exact checks regress, and multi-second teardown tails remain visible.
Root-toolchain/platform limits and warm regressions keep this opt-in.

### 14 — Own the nested HTTP pool; separately revalidate the rebase

`1f096f5ba1` closes only the invocation's idle/unused connections before existing
graceful shutdown, preserving active draining. [Real-engine cause, negative
control and repro](nested-client-lifecycle-results.md) identify a 5.8-second
unused-new-connection tail. Sixty pairs show no typical-path gain, but baseline
has 3/60 samples above two seconds versus candidate 0/60. Tests cover ownership,
errors and cancellation. `d3e1c431f7` records a separate f78-based rebuild and
correctness cohort, not another optimization: app/library native overhead stays
around 548/544 ms; cold overhead remains 19.49 seconds in that asymmetric setup.

### 15 — Evaluate a stored immutable base; do not adopt on weak edit evidence

Test a private stored Container field with normal result attachment against a
reconstructed getter. [Variant creation, guards and paired evidence](stored-toolchain-results.md)
show 23.463 ms paired saving on 60 exact pairs, but only 5.313/2.739 ms app/library
savings on 15 novel-edit pairs each, with wide ranges. Actual exec/rebuild checks
pass; the graph sheds two POSTs. Getter remains the default. No cold causal
gain, general moving-tag contract or meaningful edit-path win is established.

### 16 — Narrow engine discovery without changing its ownership policy

Pass escaped name-filter hints to Docker-like backends; retain the exact local
predicate and Apple full-list fallback. Cleanup enabled still discovers old
engines; cleanup disabled needs only the named engine. [Repro and backend/trace
validation](engine-discovery-results.md) show 162.834 ms paired median savings,
60/60 wins, specifically for prepared image-managed **cleanup=false** exact
checks. The separate default-cleanup list control saves about 35 ms, not a
proven whole-CLI default-UX gain. Cross-backend runtime coverage remains limited.

### 17 — Preserve a single generator's immutable snapshots

Avoid a Git merge when there is only one result, retaining ordinary DagQL
Before/After selections, root `.git` exclusion and skipped-module validation.
The [pilot, failure and correctness record](../bench-rust-generators/results.md)
plus commit body retain a failing baseline permission test and 25 passing
focused tests. This fixes metadata damage and removes redundant merge work;
branch 18 supplies the completed larger measurement. Nested-cwd import,
metadata-only IsEmpty and multiple-generator limitations are not fixed here.

### 18 — Record truthful full-artifact generator edits

Add Cargo >=1.91 split-build-dir prototype, selected immutable outputs, owned
`target/dagger`, strict archive checks and stable Git-root provenance. The
[portable harness instructions](../bench-rust-generators/README.md) and
[completed n=30 result](../bench-rust-generators/stable-root-results.md) retain
649.438/1521.509 ms paired app/library savings, 30/30 wins each; candidate still
adds **1152.251/1437.164 ms over native**. All output/behavior guards pass;
119/124 timed gates pass and five remain rejected. Archives are naming-only
equivalent, not raw-equal. Earlier failed namespace-changing diagnostic run
remains in the record. This is a bounded fixture, not general Rust support.

### 19 — Skip an unused preview for explicit apply only

Select existing path lists in one request instead of generating undisplayed
diffStats. Keep prompt/no-apply previews and export callbacks unchanged.
[Same-engine repro and functional limits](../bench-rust-generators/cli-comparison-results.md)
record matched CLIs, path/cancellation tests and the shared preexisting empty-dir
Workspace export failure. Certified pairs save 33.786/215.271 ms in analyzing
(n=29/22), not all process variation. In n=30 whole-process comparisons, app
paired saving is only 21.491 ms (16/30 wins); library 253.327 ms (26/30).
The earlier roughly 180 ms app pilot did not hold.

### 20 — Preserve the same-engine CLI evidence and regressions

Extend the guarded benchmark to distinct verified CLIs against one verified
runner, without the engine comparison's baseline permission allowance. The
[report, commands and CSV links](../bench-rust-generators/cli-comparison-results.md)
retain 40 pure guards, all six orders, all outputs and every timing. Complete
gates pass 112/124 timed and 124/124 diagnostics; missing-marker timings stay,
rankings are rejected. Native gaps remain **1312.607/1538.322 ms**. This is the
same cohort as branch 19, not another gain. Measurements remain on archived
fd9 binaries; source rebasing alone does not make them ff626 runtime results.

## Uncommitted diagnostic work outside this stack

Status snapshot on 2026-09-11 after the diagnostic Rust pilot `2gqxbin_`, not
durable implementations or approved production changes. These have **no
branch/commit in the inventory above**.
The named local artifacts are provenance locators only; before relying on any
result publicly, commit a reviewed reproducer and sanitized evidence separately.
No raw traces, credentials, binaries or private analyzer code are added here.

| Experiment | Local status / boundary | What is not established |
| --- | --- | --- |
| Stargz smaller read buffer and read-range instrumentation | Scratch snapshotter/runner option, supplemental DB/estargz read/Clone tests and a combined cold diagnostic; run locator `1f9b39f0e182` completed with gates passing and owned-container cleanup. One observation recorded 185,232,144 registry GET body bytes and 13.045 s raw elapsed. | No matched cold timing win, production default, cross-platform rollout or committed reproducer. Byte counts and raw elapsed are different evidence from end-user saved time. |
| Native Dang phase spans | Corrected diagnostic engine built on `f1d6824`; two print-attribution smoke checks pass after review caught hidden-span stdout attribution. Standalone app/library build/export pilot `2gqxbin_` completes: 32/32 wcprof gates, 9940 declared/received spans, 16 expected Cargo actions and 16 zero-exec diagnostics. All output guards pass, with naming-only archive equivalence and zero mode differences. | Instrumentation, not an optimization: uninstrumented control still adds 1182.259/1454.920 ms paired median over native (n=3 each). Nested proxy parenting prevents treating phase residuals as pure parsing CPU time. Local source/evidence are not yet a committed reproducer. |
| Client connection/dial diagnostics | Matched CLIs and eight fake-connector tests built/pass on `f1d6824`; real standalone pilot `zyvxl_bi` completes with 32/32 wcprof gates, 9651 declared/received spans and all output guards passing. The first foreground headers-to-query-handler boundary is 39.646 ms median over six diagnostic builds; reused-query median is 0.289 ms over 24 requests. | No accepted shared-pool redesign or demonstrated platform speedup. The boundary includes tunnel readiness and dispatch, not just dialing. Do not confuse this with the committed invocation-local fix in branch 14; no cold or cross-platform win is established. |
| SSE / wcprof final-carrier diagnostic | Local current-source diagnostic reproduces the producer/drain boundary; a producer-completion design is recorded. | No production lifecycle fix. Waiting at the wrong active-connection boundary can deadlock; bounded drain/completeness behavior requires separate validation. |

Source-only artifact export/mirror and copy-on-write investigations also remain
local design evidence, not landed optimizations. The former proposes preserving
host edits and existing ownership if export state can inform later imports;
the latter rejected a manual clone patch because the existing Go copy path can
already use kernel `copy_file_range`. No runtime filesystem conclusion or speed
claim follows from those source reviews.

## 22 — Evaluate invocation-local Dang parse reuse

`perf/rust-22-dang-parse-once-evaluation` follows branch 21 at
`540a1b1a1305b728aba33e9f78635e2c86d034e1`. This is an **experimental patch and
evidence bundle**, not an active dependency replacement or a shipped runtime
change. The [evaluation and reproduction](../bench-dang-parse-once/README.md)
retain the proposed additive Dang library API, Dagger SDK integration and their
focused tests. Production integration requires a reviewed/released Dang library
and a normal dependency update; the local replacement is only build scaffolding.

The SDK inspects the directory parser's fresh, invocation-local file blocks to
prepare self-types, removing its second source parse. It does not retain ASTs,
reuse a client's interpreter environment, or change Dagger cache identity.
Library/SDK focused tests and 36 reported integration cases pass. Standalone
smoke results retain four successful-print UI expectation failures on both
engines; subsequent log-ownership checks do not erase those original failures.

The larger full-artifact generator comparison has 30 novel edits per scenario:
paired median savings are 93.702 ms for application edits (29/30 wins) and
93.491 ms for workspace-library edits (23/30 wins). All output/freshness/mode
checks pass. Maintained wcprof accepts 246/248 captures; two candidate timed
captures lack final markers and remain rejected. All timings and regressions
remain included. Do not add this result to gains from other cohorts.

The candidate still adds paired median 976.151/1208.128 ms over containerized
native Cargo on application/library edits. This is not a native win, cold/check
result, external dependency upgrade, or general Rust/module/platform validation.
The measured source is `bfb0c200ef` on upstream `9b235855` plus the supplied
prototype patches, with one identical CLI on both sides. Upstream has since
advanced to `b8151c1f` (setup-prompt input); none of these measurements used that
newer source. Exact identities, tails, rejected gates and portability limits are
in the linked report. The full first-use and developer-loop goal remains unmet.

## Maintenance contract

For each new branch, add its parent/tip and link a tracked report with context,
change, runnable prerequisites/repro, correctness checks, frozen measured
identities, raw timing CSVs where safe, gate counts and explicit limitations.
Distinguish implementation, experiment retained-but-not-adopted, and evidence-only
changes. Keep historical rows intact when adding a new cohort or mapping after
a rebase. Do not turn local-only diagnostics into claimed shipped improvements.
