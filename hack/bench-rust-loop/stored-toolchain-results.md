# Stored immutable Rust base: exact reuse and novel-edit evaluation

The one-character stored-field change removes repeated graph construction, but
these sequential batches do **not** establish an edit-performance win or a
causal cold-start improvement. The same-engine alternating exact-hit comparison below is separate from
these cold/invalidation batches.

## Inputs and reproducibility

- Before/getter: `/tmp/dagger-rust-loop-y_x3jq7r`.
- After/stored field: `/tmp/dagger-rust-loop-20sue6kf`.
- Both CLI SHA256: `5b141b49863e23dd645620e61b3ca5049b166d4cbdd46584a8f906bd592cb1e5`.
- Both engine image: `sha256:fbcee56b446bf162ad37197cafd8b81f6a42d2afdc9994e03f09041de85e02b7`.
- Harness source: `a03e923329c1118fc28a634839ab06e27a44c3bc`, source diff
  `7254c76f3c729237a8840272110c3cd0a0c7fa10cacdc60bef2fe42f89158987`.
- Both use the same pinned ripgrep revision, digest-pinned Rust image, root
  rustfmt toolchain configuration, pinned Debian sync packages, and Cargo flags.
- Each has an independent empty engine volume/CLI state and new source/target/
  registry cache namespaces. Docker images, CLI, local module sources and host
  OS caches are already available; this is not full installation onboarding.
- Before completes first, then after. Native/Dagger order alternates inside
  each edit batch, but both single dependency upgrades run native first.

Complete per-sample timings and paired native overhead are retained in
`/tmp/dagger-rust-stored-base-analysis-timings.csv`. Provenance, all process exit
codes, package sets and capture boundaries are in the sibling `-summary.json`.

## Whole-process measurements

All values below are milliseconds. Brackets are observed min–max, not confidence
intervals. Overhead is the median of per-sample Dagger-minus-native differences,
not the difference of independently computed medians.

| Scenario | n/variant | Native before / after medians | Dagger before median [range] | Dagger after median [range] | Paired overhead before / after |
|---|---:|---:|---:|---:|---:|
| Exact | 5 | 121.03 / 118.21 | 477.28 [436.02–534.66] | 466.24 [436.58–598.26] | 360.36 / 347.61 |
| Application edit | 5 | 313.43 / 296.36 | 866.56 [789.46–937.25] | 910.17 [876.07–923.79] | 575.32 / 595.52 |
| Workspace-library edit | 5 | 451.95 / 460.01 | 1030.87 [1012.81–1164.91] | 1041.87 [967.69–1077.57] | 565.07 / 590.54 |
| External bstr upgrade | 1 | 1740.13 / 1613.33 | 2231.38 | 2121.06 | 491.26 / 507.73 |
| Upgrade followup | 1 | 125.25 / 120.82 | 447.77 | 424.69 | 322.51 / 303.87 |

The application/library/dependency overhead medians are slightly worse after
the change in these batches. Do not infer an improvement from the lower raw
external-upgrade Dagger duration: native also became faster by more.

Observed first check is 46399.35 before and 43834.99 after; provisioning plus
check is 46642.28 and 44040.90. Native first checks are 7866.47 and 6457.22.
Network/compiler variability and batch order prohibit attributing that cold
difference to stored state.

## Complete OTel coverage

Raw source: `/tmp/dagger-rust-stored-base-018193-otel.jsonl`.
Each selected trace is extracted whole by trace ID, not cut at a time boundary.
Maintained `/tmp/dagger-rust-wcprof-otel` analyzed all ten captures. All gates
PASS: one root, no open/missing/orphaned spans, no unresolved/malformed waits,
no cycles, and zero dropped links/events. Declared engine-span counts exactly
match received counts. Unique spans include one completeness marker that the
analyzer does not count as an op.

| Variant / sample | Process | Before root | Root | After root | Ops | Declared/received | Replay drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| Before first check | 46399.35 | 29.31 | 46362.07 | 7.98 | 304 | 289/289 | -1.5% |
| After first check | 43834.99 | 39.58 | 43788.55 | 6.86 | 305 | 290/290 | -1.6% |
| Before exact-2 | 534.39 | 26.13 | 495.52 | 12.75 | 169 | 154/154 | -0.1% |
| After exact-2 | 449.15 | 27.71 | 412.49 | 8.96 | 148 | 133/133 | -0.1% |
| Before application-2 | 866.56 | 27.03 | 834.17 | 5.37 | 194 | 179/179 | -0.0% |
| After application-2 | 876.07 | 27.61 | 843.98 | 4.48 | 173 | 158/158 | -0.0% |
| Before library-2 | 1164.91 | 30.19 | 1128.86 | 5.87 | 194 | 179/179 | -0.0% |
| After library-2 | 967.69 | 26.32 | 936.55 | 4.83 | 173 | 158/158 | -0.0% |
| Before dependency upgrade | 2231.38 | 28.59 | 2197.76 | 5.03 | 195 | 180/180 | -0.0% |
| After dependency upgrade | 2121.06 | 27.85 | 2086.79 | 6.42 | 174 | 159/159 | -0.0% |

Every capture has sibling `-trace.jsonl`, `-gate.txt`, `-analysis.txt` and
`-boundaries.json` files under `/tmp/dagger-rust-stored-base-analysis-*`.
Wall-clock envelope rounding can differ by microseconds from monotonic duration.

## Confirmed graph/query change

Engine debug requests in each measured process window show:

- Getter: ten Dang GraphQL requests per check. Two resolve HTTP package File
  IDs; the final query reconstructs `container.from → withMountedFile ×2 →
  withExec(dpkg)` before the unchanged project-toolchain/Cargo suffix.
- Stored field: eight per subsequent check. Neither HTTP input nor the base
  prefix is reconstructed. The final query starts from the retained Container
  handle `EhII7iASDQoJQ29udGFpbmVyGAE=`. The same handle is observed in first use,
  exact, application, library and external-dependency sessions on that engine.
- First use adds one request (ten → eleven): constructor serialization submits
  the base chain ending in `id`, and the check resumes from that node.
- Warm/edit traces remove 21 spans: the base prefix, two HTTP calls and their
  internal state operations, two POST requests and four publishResult spans.
  Query.node lookup is not separately surfaced in this OTel representation; the native
  profile records four → five node lookups, consistent with the retained base.
- Constructor wall shifts from 62 ms to 1.65 s on first use, with self-time
  62.0 → 88.7 ms. Metadata resolution/ID attachment moves earlier; the full
  operation still pays the cost. Core container execution remains lazy.

The selected application sample has almost identical shell time (379.5 vs
381.0 ms) and Rust.check self-time (52.2 vs53.7 ms). ModuleSource.asModule self
time is 43.2 vs 59.6 ms. Thus the smaller graph is real but does not imply a
measurable whole-process improvement in that sample.

First-use payload delivery still dominates: longest blob GET 28.85 vs 26.97 s,
image unpacking 4.52 vs 4.67 s, Cargo/sync shell approximately 7.00 vs 6.59 s,
rustup 1.06 vs 0.72 s. These are observed inclusive/self measurements, not additive
independent savings estimates. Cold replay itself drifts about 0.69 s; do not
turn profiler what-ifs into causal cold gains.

## Correctness evidence

- All five application edits in each variant rebuild only ripgrep, identically
  to native (ten comparisons total).
- All five library edits in each rebuild grep-printer, grep and ripgrep,
  identically to native (ten comparisons total).
- Each bstr 1.12.0 → 1.13.0 application dependency upgrade rebuilds the same ten
  package/version pairs on native and Dagger. memchr remains absent from the
  rebuilt set. Both variants' dependency sets are identical.
- Script guards verify the intended lockfile package transition and unchanged
  locked inputs after execution. Both runs reach the deliberate failure,
  repair, old-failing-source revisit and repair-revisit with expected exits.
- Exact diagnostic check-log returns previously cached Cargo stderr, which
  includes first-build Checking lines. Those are historical output, not actual
  reexecution. The selected complete exact traces contain no exec phase. Raw
  exact log-set comparison is explicitly marked not applicable in the summary.

This does not prove artifacts/build/tests/clippy/fmt, arbitrary toolchains,
mutable image tags, macOS or remote-engine behavior. Root's separate toolchain
correctness runs are not silently included in this report's measurements.

## Native recorder scope

The six populated native dumps are separate profiled repair/exact/application
diagnostics, not captures of the selected unprofiled headline samples. All have
zero dropped events and open ops; replay drift is -0.0%. Before profiles have
693–736 ops and 12 roots; after 663–706 ops and 10 roots. Their multiple independent
request roots omit CLI/transport lifecycle and cross-query causal ownership.
For example, exact recorder makespans 199.6/207.2 ms sit inside process times
436.90/435.46 ms. Do not present recorder makespan as end-to-end latency.

Both `revisit.wcprof` dumps contain zero events because that interval is not
profile-enabled. They are not evidence about revisit cost or completeness.
No first-check native dump exists (`first_check_profiled=false`); OTel supplies
first-use coverage. Maintained `/tmp/dagger-rust-wcprof-current` analyzed the
native captures; raw sources remain in their run directories.

## Dagger design boundary

This is an opt-in module experiment, not a new engine cache. The only module
change is `let toolchain: Container! {` to `let toolchain: Container! = {`.
Dang serializes the private Container; normal ModuleObject dependency attachment
retains its result closure, and subsequent invocations rebind it through their
own client. Container exec remains lazy. Workspace/source, root toolchain files
and mutable source/target/registry caches remain action inputs, outside stored
state. Source reconciliation and Cargo still execute together under existing
LOCKED mounts. No session/workspace cache, egraph bypass, persistence root,
worker, resident CLI, or garbage-collection exception is introduced.

The fixture enforces digest-pinned images. Do not generalize this to moving
tags: a cached constructor can bypass Container.from's per-session tag refresh.
Changed image/settings, restart, pruning and concurrency need dedicated coverage
before this becomes a general module default. Caching today's inferred Dang AST
is also not an acceptable substitute: it contains invocation-bound clients and
mutable type/static state. Any future compiled representation must separate
immutable compilation from fresh invocation bindings.

The committed fixture keeps its getter default. The patch and variant option
preserve the experiment without silently promoting it to the official module.

## Same-engine exact-hit comparison

Run `/tmp/dagger-rust-cli-pair-u3do49w1`: 60 alternating ordinary standalone
pairs, one retained/excluded warmup per side (7351.928 and 6427.653ms), same
CLI and main engine identified above. Rust sources were compared byte-for-byte,
excluding Git and Dagger configuration; only module selection and isolated cache
namespaces differ. The engine's toolchain image was already prepared by separate
correctness tests. Warmups create each workspace's target results. There is no
cold, native-Cargo or invalidation claim from this comparison.

Native profiling is disabled; complete localhost OTel remains enabled on both
sides. DO_NOT_TRACK=1 and the isolated/no-cloud environment remain diagnostic
settings, not an assertion about default analytics behavior. No competing build,
test or analyzer from this work ran during measured pairs.

| Metric (ms) | Getter | Stored field |
| --- | ---: | ---: |
| Median | 473.305 | 433.850 |
| Mean | 473.331 | 449.804 |
| Minimum | 411.752 | 404.289 |
| Maximum | 609.823 | 556.454 |
| Nearest-rank p95 | 552.636 | 525.403 |

Median **paired** saving is 23.463ms, mean paired saving 23.527ms;
candidate is faster in 42/60 pairs. The 39.455ms difference of marginal medians
is not the paired median. All samples and warmups are in
[stored-toolchain-exact-pairs.csv](stored-toolchain-exact-pairs.csv).

Four complete traces (before-59, after-26 central observations; before-19,
after-4 maxima) pass maintained wcprof gates with zero losses and replay drift
rounding to -0.1%/-0.0%. Selected before/after traces are not chronological pairs.
All Cargo/toolchain exec recipes hit cache; actual total HTTP POSTs fall 12→10
(10→8 nested), and operations fall 169→148. Central observed Rust.check self
is 71.5→55.6ms, while maxima are 87.7→83.0ms: this is not a measured interpreter
compiler speedup. ModuleSource.asModule still executes and costs about 45–49ms;
candidate central connection establishment is 134.5ms. Envelopes and nested
phases must not be added together.

Artifacts: `/tmp/dagger-rust-stored-base-exact-analysis-*`, including the
summary, four complete traces, boundaries, gates and analyzer reports.

## Current-main build and correctness validation

The 14 existing branches were mechanically rebased from f78bf2c58 onto upstream
`018193f5a9991a21626fc77a31127106d793e3f3`; range-diff reports all 16 commits
unchanged. The old tip is preserved by `archive-rust-perf-before-018193f5a9`.
The rebuilt source tip is `a03e923329c1118fc28a634839ab06e27a44c3bc`.
CLI reports dirty (the preserved experimental bundle is untracked); CLI/engine
identities above identify the actual tested build.

Build with the repository's pinned dev deployment, using an unused owned name
and separate output, not the normal dev engine:

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call \
  dev --docker=unix:///var/run/docker.sock deploy \
  --name=dagger-engine.rust-main-018193f5a9 \
  --image=localhost/dagger-engine.rust-main-018193f5a9 \
  --platform=linux/amd64 --debug-endpoint=false \
  --output /tmp/dagger-rust-main-018193f5a9-bin
```

The loader removes its named placeholder before deployment: create only an
owned stopped placeholder after checking that name/volume are unused, as in
the earlier HTTP-input experiment. Existing engines/caches are preserved.

Focused post-rebase validation:

- Nested-client race suite, three repeats: 21 leaf executions, 1.694s package.
- HTTP state plus private-handle retention/round-trip/attachment race cases:
  11 top-level tests, 1.173s package.
- core/workspace unit package: 0.036s.
- 15 selected CLI init/settings/module/SDK-registry groups: 0.965s.
- Four Dang integration groups (PrivateArg, MapFields, WorkspaceArg, Directives),
  workspace Init/WithInitialized and module Selection/VersionUpdate: 90.319s.
- Existing toolchain suite for each variant: eleven standalone checks and six
  direct immutable manifest reads pass. Before
  `/tmp/dagger-rust-toolchain-test-m_9011as`; after
  `/tmp/dagger-rust-toolchain-test-ki16tbrh`.

Logs: `/tmp/dagger-rust-main-018193-{shared,core,workspace-unit,cli-unit-dev,integration}.log`.
The first CLI test attempt accidentally selected PATH's installed CLI and was
terminated; only the rerun with explicit _EXPERIMENTAL_DAGGER_CLI_BIN is accepted.
The test-generated root lockfile was archived under
`/tmp/dagger-rust-main-018193-integration-dagger.lock` and its unrelated changes
removed; no version-pin updates are part of this experiment.

Main's new `dagger setup` is guidance-only. This fixture prewrites local module
configuration; it does not measure genuine `dagger install`, CLI/engine download
or complete first-user onboarding. Installation must be timed separately in
the full module, not inferred from a now-no-op reinstall.

## Reproduce the module variant

```sh
variant_root=$(mktemp -d /tmp/dagger-rust-module-variants.XXXXXX)
cp -R hack/bench-rust-loop/module "$variant_root/before"
cp -R hack/bench-rust-loop/module "$variant_root/after"
git -C "$variant_root/after" apply \
  /ABS/REPO/hack/bench-rust-loop/fixtures/stored-toolchain-base.patch

python3 hack/bench-rust-loop/run.py \
  --dagger /tmp/dagger-rust-main-018193f5a9-bin/dagger \
  --module-dir "$variant_root/before" \
  --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
  --fresh-engine sha256:fbcee56b446bf162ad37197cafd8b81f6a42d2afdc9994e03f09041de85e02b7 \
  --ripgrep /ABS/PINNED/RIPGREP --samples 5 --pinned-source-sync \
  --project-toolchain hack/bench-rust-loop/fixtures/rust-toolchain-rustfmt.toml \
  --prepare-project-toolchain --dependency-upgrade --dependency-first native
# Repeat with --module-dir "$variant_root/after"; preserve both run directories.
```

Use the clean/localhost-OTel environment above. For the exact comparison use
`compare-cli.py` with the same binary on both sides, the two resulting
workspaces, `--samples 60 -- check rust:check`, and explicitly set DAGGER_ENGINE
to the preserved main engine. The fresh-engine runs delete only their own
engine/volume; the main engine is a separate retained deployment. All raw
invalidation samples are in
[stored-toolchain-invalidation.csv](stored-toolchain-invalidation.csv).

## Same-engine alternating novel edits

Run `/tmp/dagger-rust-module-edits-htfjxy8m` uses the same rebuilt CLI and
preserved engine identified above. The two resulting ripgrep workspaces have
separate source/target cache namespaces. Each scenario has 15 alternating
measured pairs and one retained/excluded warmup pair; every pair gets a novel
run-specific edit. Local OTel is enabled, native profiling disabled, DNT=1.
No competing build, test or analyzer from this work ran during these timings.
There is no cache reset, native Cargo timing or cold claim in this comparison.

| Metric (ms) | Application | Workspace library |
| --- | ---: | ---: |
| Getter median | 851.869 | 1002.145 |
| Stored-field median | 837.842 | 1004.438 |
| Median paired saving | 5.313 | 2.739 |
| Mean paired saving | 16.938 | 3.559 |
| Paired saving min–max | -70.201–141.645 | -101.540–134.845 |
| Stored-field faster pairs | 10/15 | 8/15 |

Positive saving means the stored field won. These small paired medians amid
roughly 200ms-wide paired ranges do **not** establish a robust edit-path win.
The getter remains the default. All measured samples and warmups are retained
in [stored-toolchain-edit-pairs.csv](stored-toolchain-edit-pairs.csv).

All 60 measured check traces contain exactly one positive-duration Cargo/sync
`exec.processRun`, its `exec.run` parent and a successful container-exit event;
each side has 30 distinct executed-action digests. The four warmup checks also
execute. All 64 outside-timer `check-log` invocations contain zero Cargo exec
phases: they retrieve output from those preceding executions. Live stderr and
diagnostic phase/name/version tuples match for every measured check:

- Application: only `Compiling ripgrep 15.2.0`.
- Library: only `Checking grep-printer 0.3.1`, `Checking grep 0.4.1` and
  `Checking ripgrep 15.2.0`.

All 30 paired rebuild sets match, with no unrelated packages. All 32 edit tokens
and resulting file hashes are unique (including warmups) and reconstruct from
the preserved originals. Final source, script and process-log hashes match the
recorded metadata. All 128 process traces have one complete root within process
boundaries, matching declared/received engine spans, no orphaned/open spans and
no dropped links.

Four complete sample-8 captures pass maintained wcprof gates: no losses,
unresolved waits, cycles or unschedulable operations, replay drift -0.1%/-0.0%.
Getter captures have 194 operations/179 engine spans; stored captures 170/155.
The stable module reduction is **21 spans and two POSTs**, not 24 spans: the
first side of each pair pays three additional source-mount/lazy/publish spans,
and the second benefits from normal immutable source-mount reuse. Sample 8
runs getter first; odd samples reverse this advantage. Alternation balances it
as far as possible with 15 pairs (stored first eight times). Cargo executes
on both sides every time; that source-mount reuse is not skipped compilation.

Whole-process minus Cargo/sync shell means remain 492.285→476.996ms for
application edits and 483.261→472.696ms for library edits. This is **not** native
Cargo overhead: rsync is inside the shell and native Cargo was not timed here.
Session establishment, checks orchestration, module evaluation and
ModuleSource.asModule remain visible. Trace-consumer attribution denotes SSE
establishment/lifecycle with local capture, not telemetry flushing or exporter
CPU. Attribution buckets are not additive proven optimization savings.

Reproduce after creating the two matching workspaces above:

```sh
DAGGER_ENGINE=container://dagger-engine.rust-main-018193f5a9 \
  python3 hack/bench-rust-loop/compare-module-edits.py --execute \
    --dagger /tmp/dagger-rust-main-018193f5a9-bin/dagger \
    --before-workdir /tmp/dagger-rust-loop-y_x3jq7r/dagger \
    --after-workdir /tmp/dagger-rust-loop-20sue6kf/dagger --samples 15
```

Use the same isolated/local-OTel environment. This intentionally leaves the
benchmark copies edited; originals are preserved in the printed run directory.
The helper records the engine endpoint, not independently verified live image
identity; the separately verified deployment above supplies that provenance.
Its module hash covers main.dang and configuration, sufficient for these
two-file variants, not arbitrary recursive modules. Application and library
groups run sequentially, and diagnostic requests add outside-timer work between
pairs. No inference about build/artifact, macOS, remote or onboarding performance
follows from this experiment.

Full audit: `/tmp/dagger-rust-stored-base-edit-analysis-report.md`, sibling
`-summary.json`, `-timings.csv` and four
`-<scenario>-8-<side>-{trace.jsonl,gate.txt,analysis.txt}` captures.
