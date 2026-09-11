# Explicit apply: same-engine CLI comparison

This isolates the CLI change in `32fcabf43c`: explicit `-y` uses existing
changed-path fields instead of computing a preview it never displays. Both
CLIs use the same already-running single-generator engine. No compiler,
cache-key, session, export or module behavior changes in this comparison.

**The application pilot did not hold.** The 30-pair batch has only 16/30 app
wins and substantial order/temporal variation. Library results are stronger
at 26/30 wins, but neither workflow approaches native latency. This does not
improve the previously reported check/cold/exact-cache results.

## Reproduce and interpret the mode

Build matched control/candidate CLIs with the same compiler, flags and source
except the explicit-apply patch; use a prepared engine with the single-generator
snapshot fix. Capture live OTel as described in the main README. Then:

```sh
python3 hack/bench-rust-generators/compare-generators.py \
  --execute --compare-clis \
  --dagger /absolute/path/to/control/dagger \
  --after-dagger /absolute/path/to/candidate/dagger \
  --before-engine 'docker-image://localhost/dagger-engine.rust-single-generator-fd9?container=dagger-engine.rust-single-generator-fd9&volume=dagger-engine.rust-single-generator-fd9&cleanup=false' \
  --after-engine 'docker-image://localhost/dagger-engine.rust-single-generator-fd9?container=dagger-engine.rust-single-generator-fd9&volume=dagger-engine.rust-single-generator-fd9&cleanup=false' \
  --before-image-id sha256:f2af055e32f6e65fbabdbcee9561d9adc26cddb6c01f4b41b73058564847d174 \
  --after-image-id sha256:f2af055e32f6e65fbabdbcee9561d9adc26cddb6c01f4b41b73058564847d174 \
  --module hack/bench-rust-generators --samples 30
```

The explicit image above is the recorded local build, not a published image.
Replace it, the runner selectors and CLI paths with independently verified
matched builds. Pilot with three samples before running 30. No other builds,
tests or analyzers run during timing. These prepared, explicit runners do not
measure default engine provisioning or onboarding.

CLI mode checks named/running container ID, image ID, image-alias resolution,
PID, start time and restart count before/after. It rejects wrong/duplicate/
unknown URL options, userinfo and invalid names. It removes ambient
`DAGGER_LEAVE_OLD_ENGINE`; records both CLI hashes/versions; dispatches setup,
timed commands and diagnostics through the correct side; and rejects *every*
mode discrepancy. Existing one-CLI engine-comparison behavior is unchanged.
Only the exact owned native container is automatically removed. Source trees,
failure records and normal engine-owned caches are retained.

The harness initially failed setup with unsupported `dagger --version` in run
`/tmp/dagger-rust-generator-pair-2wvtlp0z`, before native/timed work. The retained
two-line correction uses `dagger version`; Cargo/ar still use `--version`.
All 40 pure guard tests pass on the rebased source (0.018s, not a speed claim):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s hack/bench-rust-generators -p test_compare_generators.py -v
```

## All process timings, including regressions

Run `/tmp/dagger-rust-generator-pair-9mtwsg9b`: 30 novel edits per scenario,
each of six execution orders five times; one excluded/retained warmup triple
per scenario. All values below are milliseconds. Differences and ratios are
paired; they are not differences or ratios of independently calculated medians.
Nearest-rank p95 is observation 29 at n=30. No outlier is removed.

| Edit | Control median | Candidate median | Cargo median | Paired saving median | Wins | Paired native gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Application | 1478.479 | 1539.650 | 150.443 | 21.491 | 16/30 | +1312.607 |
| Workspace library | 2035.046 | 1743.075 | 206.074 | 253.327 | 26/30 | +1538.322 |

The app candidate's separate process median is worse despite the small positive
paired saving. Medians do not distribute over subtraction; both are reported.

| Edit | Paired saving range | Mean saving | Candidate p95 / max | Paired slowdown vs Cargo |
| --- | --- | ---: | --- | ---: |
| App | -1220.121 to +2515.172 | 89.654 | 2788.177 / 4242.420 | 8.514x |
| Library | -180.588 to +1385.797 | 321.958 | 3285.659 / 3907.268 | 7.971x |

All six library order-group median savings are positive. App
candidate/control/native is 0/5 wins, median **-405.387 ms**; other order-group
medians range -26.873 to +410.952 ms. The largest apparent app win includes
1939 ms of actual-action variation; it is not a preview-saving effect. The
largest loss includes slower action, module/source, startup and outside-root
work. Native also varies: app 142.173–1670.157 ms, library 180.983–553.450 ms.
There is no recorded CPU/disk/memory/GC evidence establishing the cause of that
variation. Do not dismiss it as proven GC or remove those samples.

The preceding n=3 pilot `/tmp/dagger-rust-generator-pair-6n72c039` saved
179.620/275.007 ms paired, with native gaps +979.630/+1176.398 ms. All six
measured pairs improved. It was not order-balanced and did not establish tails;
the larger result supersedes that impression, without deleting the pilot.

## wcprof and correctness gates

Complete gates pass for **112/124 timed roots** and **124/124 diagnostics**.
The 236 accepted traces reconcile 70,962 declared/received engine spans,
with no dropped events/links, open operations, orphan parents or malformed
waits; replay drift ranges -0.0% to -0.4%. Twelve timed roots lack completion
markers, six per CLI. One exact-ID late rescan produced byte-identical traces,
still missing markers. Their process times stay in every aggregate; their
profiles are not treated as certified complete or used to repair other traces.
The trace-audit CSV records every rejection and trace ID.

Each complete timed trace certifies one correct build. All 124 timed traces
observe that build, but incomplete ones cannot prove absence of unobserved
work. Every complete diagnostic certifies zero extra execution. Application
edits rebuild only the app; library edits rebuild the library and both binaries.
All 1,488 observed namespace entries remain `mod(rust.)`; no frozen-module Git
root switch occurred. Historical cached Cargo JSON is not independent execution
proof; timed traces and diagnostic traces are checked separately.

Across complete paired profiles, analyzing-phase median savings are
**33.786 ms app (n=29)** and **215.271 ms library (n=22)**. Both sides still
have 30 observed POST queries: this is less work, not fewer round trips.
The path resolvers share `ComputePaths`' existing `sync.Once`; waiting siblings
can appear as self-time without a dedicated wait edge. Do not add their self
times/what-if savings. These numbers use the containing disjoint CLI phase.

All 62 source/artifact triples match expected dirty/fresh target sets and
observable source edits. There are 248 raw-equal executable comparisons,
248 strictly naming-only-equivalent archives (**raw unequal**, never rewritten),
372 passing behavior checks, and zero artifact/ancestor mode discrepancies.
Final retained artifact hashes were rechecked; historical generations rely on
their saved validation/log records. Outside sentinels remain unchanged. Native
exact-ID/owner cleanup completed. See the main README for archive-check limits.

Both CLIs also pass direct Changeset empty-directory add/remove and nine other
ordinary-generate functional cases, including no-apply, no-op/repeat, type and
symlink replacement, rename and failure preservation. Both fail the same
ordinary empty-directory-only Workspace export case. It reaches successful
uncached Workspace.export but does not transfer the directory; the source-backed
explanation is its file-only IsEmpty shortcut. This is a separate unresolved
correctness issue, not a full-suite pass or regression caused by this CLI patch.

## Retained compact evidence and provenance

- [All 186 timed processes](cli-30pair-timings.csv), including six warmups.
- [All 60 paired measurements](cli-30pair-paired-results.csv), with gate-aware
  phase differences, native gaps/ratios and exact trace IDs.
- [All 248 Dagger roots](cli-30pair-trace-audit.csv), including diagnostics and
  rejected captures. The extractor's historical `kind=pilot` field denotes the
  Rust benchmark family, not n=3; sample count/order is explicit above.
- [Earlier pilot timings](cli-pilot-timings.csv), retained separately.

CSV values are copied unchanged; line endings are normalized to LF. Full local
raw records, gates, phase evidence and original/late extractions are retained
under `/tmp/dagger-rust-auto-apply-cli-30pairs-analysis-`; the maintained private
analyzer's implementation is not copied into this repository.

Matched builds used Go 1.26.8, CGO=0, linux/amd64 v1 and identical linker flags.
CLI source base was `3f129d3b463622673bca1634f2d6bbe03e1b8b12`; engine includes
single-generator fix `38d5bbca38332172a0074665062fa4eac7650cd2`. Exact hashes:

| Input | SHA256 |
| --- | --- |
| Control CLI | `071845c9212b82739542e0edefe0536fee73f1297a4fe28ce85aedebc0b230ee` |
| Candidate CLI | `11394ac967a03857e26f2c12ac11aea3be60e4da999c126babe5048fe109089a` |
| Harness | `b3d96491306750aa0e9a81c549ea4427846c0ff6ea0be964a05597d84903aa38` |
| Module | `48c95bb11c503e94cda52d61f1313f458f3813714d83acd703ed8996660f4164` |
| Rust image | `39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b` |
| Maintained analyzer | `de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba` |

The source stack was subsequently rebased onto upstream `ff626243dc`; all 20
prior patches are unchanged and only SDK-generator tracing was added upstream.
Old measured history remains fetchable from fork tag
`archive/rust-stack-fd9bc0036a-04e77e6b`. New full engine runtime validation is
pending; these remain fd9-based measurements, not latest-main results. Focused
CLI/core tests pass after rebase; tested CLI source/test bytes are unchanged.

Native here is Cargo through Docker exec, not host-native Cargo. It does not
perform Dagger's metadata, immutable selection/export or wcprof instrumentation.
Normal Cargo debug/features/toolchain settings were retained. Local live OTel
and DO_NOT_TRACK were enabled; these are instrumented Linux/amd64 timings, not
macOS, remote, cold-install, faster-than-native or official-module-completion claims.
