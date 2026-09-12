# Invocation-local parsed-source reuse

This is an experiment, not shipping dependency wiring or a new cache. The
engine patch targets reviewed stack `db9d005c715ac9d146780d783faf7f7b55d23e5e`,
based on main `6bf59d50654ce9244ebeee1cc090b7dce3fe3083`. The separate diagnostic
patch must **not** be applied to either side of the performance comparison.

## Change and upstream boundary

The SDK first parsed every source file to discover its own public type names,
then the Dang directory runner parsed those files again for normal evaluation.
[dang.patch](dang.patch), against `github.com/vito/dang/v2@v2.1.3`, adds a single
optional `DirectoryOptions.BeforeInference` callback and `RunDirWithOptions` /
`DeclareDirWithOptions` entrypoints. The old entrypoints retain their signatures
and delegate with empty options. [engine.patch](engine.patch) uses the callback
to inspect the runner's freshly parsed files, removing the second directory
read and parser pass. It includes the focused SDK regression tests.

The callback runs after successful deterministic directory parsing and before
inference/evaluation, inside the existing service registry ownership lifetime.
Parsed forms are borrowed, inspection-only, and must not be retained, mutated
or shared with another invocation. Errors preserve wrapping identity. Existing
empty-directory and parse-error behavior is retained. File-local imports and
normal directory declaration/evaluation remain the library's responsibility;
the engine does not reimplement those internals.

All public object, interface, enum **and scalar** names, the main-name fallback,
namespacing and existing schema entries remain. IncludeSelfInDeps alone is not
enough to skip discovery: source-only scalar names need preparation too.
The hook does not clear the existing import schema-module cache. Schema
preparation must precede initialization of that cache, or use a fresh import
context as the SDK already does for each invocation.

No graph identity, persistent AST/schema/result cache, Cargo action, source
filter, session reuse, lease or GC behavior changes. Frozen Dang v1 and shared
dispatch code are unchanged. A Dang API review/release and a normal version
bump are required before an upstream engine change could compile. The local
`replace` and copied dependency used below are **only** experiment scaffolding;
neither is proposed as a shipping engine dependency. No maintainer approval is
implied.

## Validation completed before measurement

The library patch includes tests for reuse of the parsed forms, stable multi-file
ordering, pre-inference schema preparation, errors/cancellation identity,
owned versus inherited service registry cleanup, empty directories and fresh
invocation AST/schema state. Cleanup tests check registry ownership without
starting real service processes. SDK tests preserve all declaration kinds,
scalar-name synthesis, namespacing, existing entries and equivalence with the
old direct file parser's discovered names.

Focused SDK and library tests passed three race-enabled repetitions. The first
test attempt is retained: a new fixture reused an already initialized schema
cache after an expected inference failure. The fixture was corrected to use
fresh import contexts, matching SDK ownership. No runtime cache behavior was
changed to make that test pass.

```sh
# From the experimental engine source, after applying the patches and local
# development-only Dang replacement. Pin Go 1.26.8 as in the retained build.
go test -mod=readonly -race ./core/sdk/dang/v2 github.com/vito/dang/v2/pkg/dang \
  -run '^(TestParsed|TestDirectoryPreparation|TestDeclareDir|TestRunDir)' \
  -count=3 -timeout=120s

# Supported engine build + selected integration path; no plain-progress opt-out.
dagger api call engine-dev test --pkg=./core/integration \
  --run='^TestDang$/^Test(SelfCallReturningOwnType|Enums|Interfaces|Scalars|VersionedSyntax|CoreTypeShadowing|Directives|Mismatch)$' \
  --parallel=1 --timeout=5m --count=1 --test-verbose=true
```

The supported integration command exited successfully, followed by a supported
dev deploy and a query smoke check. The retained TUI log reports one passing
parent suite; it does not separately enumerate leaf pass counts. The selection
matches eight suite methods in source. Current fixtures exercise v2; the
versioned-syntax method also retains the intentionally v1 legacy fixture.
The original log is retained, including its inner-engine service teardown
error row despite the passing outer test command; this is not erased from the
evidence or presented as a clean service-lifecycle certification.
This is not a full integration-suite or concurrent GraphQL-client certification.

## Paired measurement protocol

Owner: `/tmp/dagger-dang-parse-reuse.JjOIpfha`. Retained single-use controllers
and manifests pin every changed source/dependency file, CLI, module, adapter,
toolchain and engine image. Create fresh owned paths for a rerun; do not append
to an old capture or reuse a partially completed cohort.

```sh
python3 /tmp/dagger-dang-parse-reuse.JjOIpfha/build.py --plan
python3 /tmp/dagger-dang-parse-reuse.JjOIpfha/build.py --execute
python3 /tmp/dagger-dang-parse-reuse.JjOIpfha/run.py --execute
python3 /tmp/dagger-dang-parse-reuse.JjOIpfha/analyze.py COHORT
python3 /tmp/dagger-dang-parse-reuse.JjOIpfha/summarize.py COHORT
```

The two patches check-apply independently to their exact base sources. For the
experiment only, copy stock Dang into a writable local dependency, apply its
patch, and use `replace github.com/vito/dang/v2 => ./internal/bench-dang-parse-reuse/dang`
in the isolated engine checkout. Never patch the shared Go module cache.

Three independent AB/BA/AB engine pairs use the **same** readiness CLI. Each run
excludes the separate verified-image-stream experiment on both sides: this is
not a cumulative best-stack scorecard. Each run
owns fresh engine, Cargo and CLI state, three novel application edits, three
novel workspace-library edits, and one actual bstr 1.12.0→1.13.0 upgrade. Summarize
warm repeats within each run first: these are three independent pairs, not nine.
Checks use ordinary separate CLI processes, with failure/repair/revisit and
engine-restart gates. Unchanged workload/diagnostic commands verify actual
affected crates and selected dependency versions on both sides.

First-check and external-upgrade timings include wcprof; other timed warm flows
do not. Complete OTel captures and post-timer diagnostic invocations are enabled
on both treatments. Keep structural/correctness capture acceptance distinct from
replay-drift accuracy. Do not use inaccurate replay what-ifs to explain cold
differences.

Limitations: CLI, Docker, engine image, module and native toolchain image are
preinstalled. First check has an empty Dagger engine, but is not complete
installation. Native runs via `docker exec` in the matched image, not on the bare
host. Host page caches and public CDN caches are not purged. Native follows
Dagger for initial compilation; later comparisons preserve the pinned order.
No artifact, formatting, Clippy, test-command, macOS or remote performance claim.
Do not sum this experiment's savings with other cohorts.

The separate post-recovery application diagnostic can rebuild three crates
because an immutable cached repair does not rewind a mutable Cargo cache left
by the previous failure. Ordinary **timed** application edits must still rebuild
only ripgrep, matching native; timed library edits rebuild grep-printer/grep/
ripgrep. No timing or expected-work gate is relaxed for that diagnostic history.

## Results: mixed, not a broad promotion

All six runs completed. All 36 wcprof capture/execution/package/image-byte gates,
18 cache analyses and 36 ordinary warm rebuild audits passed. Both sides fully
downloaded and unpacked the same 316,873,658 compressed Rust-image bytes in each
empty engine. Receiver shutdown and cleanup of each of the six benchmark-owned
container/volume groups were verified. Retained raw telemetry is 42,674,429 bytes.
[validation.json](validation.json) includes every gate and the full raw/report/
build hashes; [comparison.json](comparison.json) retains every timing observation,
run median, paired difference and tail.

Milliseconds below. Positive paired savings mean the candidate was faster.
Marginal medians and median paired native overhead are computed separately;
subtracting two marginal median columns need not reproduce median overhead.

| Flow | Candidate CLI | Native | Native overhead | Paired CLI saving, median (min…max) | Faster pairs |
|---|---:|---:|---:|---:|---:|
| First check, profiled | 17,905.277 | 7,337.746 | +10,328.994 | +1,280.203 (−404.706…+2,639.041) | 2/3 |
| Provision + first check | 18,157.181 | 7,337.746 | +10,544.544 | +1,281.765 (−393.932…+2,598.223) | 2/3 |
| Ordinary unchanged | 444.536 | 120.354 | +324.272 | +0.457 (−19.910…+12.755) | 2/3 |
| Application edit | 802.311 | 290.081 | +512.682 | +22.274 (−27.285…+52.819) | 2/3 |
| Workspace-library edit | 984.637 | 475.563 | +524.470 | −0.828 (−8.689…+11.019) | 1/3 |
| External upgrade, profiled | 2,144.006 | 1,637.181 | +547.717 | +23.355 (−190.705…+88.652) | 2/3 |
| Unchanged after upgrade | 412.840 | 118.555 | +294.286 | +41.009 (+4.458…+47.453) | 3/3 |

The ordinary exact result is effectively flat. Application edits are promising
but not consistent across these three pairs; library edits are flat/slightly
worse. The profiled upgrade's native-overhead difference actually **regresses**
by a median 99.430 ms (candidate improves native overhead in only 1/3 pairs),
despite the positive median raw CLI difference. Keep that native-normalized
loss, including the third pair's 190.705 ms raw CLI regression. Every candidate
flow remains slower than native; no overall goal or first-use target is met.

The separate exact diagnostic profiles show a more consistent inner change:
ModuleSource.asModule self-time falls in all three pairs by 9.6/12.5/15.9 ms;
Rust.check self-time falls by 9.9/9.5/9.5 ms. The median **profiled diagnostic**
CLI saving is 15.579 ms (all three positive). Those are different observations
from the ordinary unchanged timings above; they do not replace the flat headline.
Self-time here is wcprof attribution, including uninstrumented SDK phases—not
CPU measurements or an additive end-to-end estimate. [attribution.json](attribution.json)
retains rounded analyzer table values and source hashes for all 36 profiles.

Do not attribute the apparent 1.280 s cold saving to this parser change. The
first two control connection spans take 1.501/1.520 s versus 0.464/0.472 s for
their candidates, **before any Dang source parsing**. The third pair loses
404.706 ms; its Dagger Cargo action is also 597.553 ms slower. Image-delivery
envelopes are roughly 8.2–9.2 s, with no consistent improvement. Native cold
compilation also varies substantially, including the candidate's final 8.411 s
sample. These are observed differences, not a complete causal partition.

Warm/restart replay drift is −0.0%…−0.1%; cold drift is −4.2%…−4.9% despite
structurally complete captures. Cold phase walls and actual process timings
remain evidence, but cold replay what-if savings are not accurate enough for
quantitative attribution. The analyzer's capture-pass flag is not a replay-
accuracy certification.

Conclusion: the unnecessary parse work is removed with focused correctness
coverage and lower observed inner execution cost. The end-to-end effect is
limited/mixed, so preserve this as an API/performance experiment rather than
adding its best numbers to a winning-stack claim. Remaining connection, source
sync and toolchain-delivery costs require their own controlled changes.
