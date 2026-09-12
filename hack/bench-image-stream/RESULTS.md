# Verified download overlap: measured result and remaining gap

## Comparison and cache state

Three paired runs, sequential AB/BA/AB, one Linux host and the same direct public
registry route. A is the previous bounded-hash engine; B adds corrected download/
extraction overlap. Each sample gets fresh owned engine and Cargo state. The
fixed CLI, module, Rust image, project, flags, adapter and route are identical.
Ordinary standalone checks are used, not a listener or persistent CLI session.

Docker, the CLI, engine images, local module and native Rust image are already
installed. Host page/CDN caches are not purged. Native runs after Dagger inside
the first-use sample and includes docker exec in the matched Rust image; it is
not a bare-host comparison. First-check samples are profiled. Warm headline
timings and their later diagnostic profiles are distinct. These data establish
engine-cold behavior, **not installation from nothing or remote/macOS results**.

## Corrected cohort: all samples, seconds

| Pair/order | A first check | B first check | Paired saving | A provision + check | B provision + check |
|---|---:|---:|---:|---:|---:|
| 0 AB | 15.964615 | 15.030882 | 0.933733 | 16.178845 | 15.277932 |
| 1 BA | 16.458652 | 14.181931 | 2.276721 | 16.670878 | 14.393862 |
| 2 AB | 23.624466 | 13.817441 | 9.807026 | 24.451988 | 14.022321 |

The median paired first-check saving is 2.276721 s (3/3 favorable). The median
paired reduction in provisioning-inclusive overhead relative to each sample's
native reference is 2.087345 s. Do not subtract unrelated marginal medians or
add these gains to measurements from older cohorts.

Candidate provisioning-plus-check median is 14.393862 s, range
14.022321–15.277932 s. Its native references are 7.042149, 6.844125 and 7.266326 s.
Median **per-run** provisioning-inclusive overhead is 7.549737 s, range
6.755995–8.235783 s. CLI alone is 1.90–2.13 times its native reference.
This still fails the 0.5–1 s cold-overhead goal by a large margin.

## Phase evidence and regressions

Image delivery A: 7.024908, 7.348714, 13.716186 s.
Image delivery B: 4.749642, 4.746661, 4.712108 s.
All B traces show actual reads of the largest layer before that layer's own
download finishes. Both sides download and unpack all **316,873,658 compressed
bytes**, across the same two descriptors. No verification or byte reduction
accounts for this result. Streaming unpack envelopes include network waits;
phase medians cannot be added or treated as isolated CPU work.

The last control's 13.716186 s image delivery is an outlier retained in the
headline pair. Its cause is not established; not all 9.807026 s of that pair's
saving can be attributed causally to the patch. Three pairs on one host do not
establish tails, broad reliability or a global speedup.

Cargo inside Dagger was **slower in all three B samples**: paired losses
372.813, 244.068 and 428.559 ms. Its cause is not established. Warm paired native
overhead also worsened at the median: exact +9.531 ms, application +18.561 ms,
workspace library +16.106 ms (each unfavorable in 2/3 pairs). No warm win is claimed.

| Candidate warm flow | Native median | Dagger median | Median per-run overhead |
|---|---:|---:|---:|
| Unchanged check | 0.118027 | 0.523410 | 0.405383 |
| Application edit | 0.318160 | 0.878008 | 0.585932 |
| Workspace-library edit | 0.457775 | 1.032672 | 0.560357 |

These are check results, not new artifact, fmt, clippy, tests or actual external
library-upgrade measurements. All remain slower than native. Next performance
work must address ordinary CLI connection/query overhead and remaining cold
delivery/setup costs; exact cache hits alone do not satisfy the goal.

## wcprof and correctness gates

All 30 wcprof completeness/count/actual-execution/progress/native-package/byte
gates and all 18 cache analyses passed; zero rejected runs. Cold replay drift
was −3.5% to −6.2%, so replay what-ifs remain hypotheses, not measured savings.
Full process timing includes work outside the root span. The preserved workload
also checks real edits, failures, repair/revisit and engine-restart reuse.

Final supported race suites reported 216 passing snapshot results, 108 normal
real-resolver results and 21 large real-resolver results. Counts include nested
groups and repetitions, not 345 independent cases. Integrity failures, truncated
input, cancellation, ownership, release and GC gates remain enabled. The large
case uses the default decoder and exceeds the 8 MiB hash-worker threshold.

The progress-reader race was independently reproduced against stock containerd
apply.go using a read-only overlay, then five focused cases passed ten race
repetitions with the narrow fix. An owned-pipe regression failed before its
Close/fence fix; those cases plus the optional reader contract passed ten race
repetitions afterwards. See the parent evidence branch for the stock-only fix.
Supported tests, normal dev deployment and a fixed-CLI query passed before timing.

Retained warnings include invalid local git remote, root as-sdk migration and
outer nested-service teardown ERROR despite successful tests. Earlier failures
are not erased by the passing final run. No production-readiness claim is made.

## Initial candidate: retained, not promoted

The previous candidate's first three pairs saved 3.633299, 2.772238 and
**−5.898349 s**. Its slow B delivery was 11.006 s versus 4.644–4.683 s in the
other B runs; the cause is unknown. Its median warm overhead worsened by
77.598 ms exact, 110.740 ms application and 18.904 ms library.

That candidate passed the initial smaller tests but subsequently failed the
10 MiB/default-decoder race gate on compressed-digest failure. It is therefore
not a correctness-validated speedup. The corrected cohort above is a fresh
comparison after the progress synchronization and private-pipe ownership fixes;
do not pool its results with the old candidate. initial-summary.json preserves
every old timing, including the losing pair.

## Reproduction and exact local evidence

Retained corrected source/build/controller root:
`/tmp/dagger-stream-reader-lifecycle.w7gTjM09`.
Measured source parent: db9d005c715ac9d146780d783faf7f7b55d23e5e, an experimental
stack based on main 6bf59d50654ce9244ebeee1cc090b7dce3fe3083.
The inert engine.patch excludes the temporary go.mod dependency replacement.

Build: `python3 /tmp/dagger-stream-reader-lifecycle.w7gTjM09/build.py --execute`.
Controller: `python3 /tmp/dagger-stream-reader-lifecycle.w7gTjM09/run-stream-pairs.py --execute`.
Both are host-specific, single-use scripts with exact source/tool/image pins
and refusal to overwrite earlier captures. Use fresh owned roots and identities
for a repeat; do not reset shared engines or edit the pinned measured source.
Controller order is ABBAAB; no tests/builds run concurrently with timing.
The controller removes only its owned temporary benchmark containers/volumes;
their absence was verified after completion. Retained dev engines remain.

Analyzer: `/tmp/dagger-streamed-cold-engine.4JZ0SlL3/analyze-stream-ab.py`.
Summarizer: `/tmp/dagger-streamed-cold-engine.4JZ0SlL3/summarize.py`.
The corrected cohort used both unchanged. They retain missing/duplicate/short
progress and per-layer overlap attribution checks; no gate was weakened.

| Artifact | SHA256 or immutable ID |
|---|---|
| A engine | 3b711dbd1020dc827a3a1e452fba01c480e924cdf6151b623f8214ca5a1abf5d |
| Corrected B engine | 848627df950f9d0211436e3210bbbf34ba97f7a1823a528880c5dace238d9a2c |
| Old B engine | 70f0b43f874a49d136f3e7e0a9b537478492b1393be20be9be98718116121df5 |
| Fixed CLI | 984c0d2e5e3f22ffb71bf8a9367b4b784120681ebc27923296adbba9817ac227 |
| Rust image | 39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b |
| Module main.dang | f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1 |
| wcprof executable | de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba |
| OTLP receiver | f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38 |
| build.py | 9cf942c6c08ee5b167f846b894d73f3b48b8e57d0031da1e9076dda61ebff332 |
| build/engine-build.json | 0ae964abb099b4811e9ea39a21516f759f9cc5b69f27f99a60d818a366f7ebb9 |
| run-stream-pairs.py | 04cc86bb0334fa1733b67c62555241614a9525ca004a552def0a61fe6660695b |
| analyze-stream-ab.py | e2725201f87b6d5d6c747e43cc02ef19b6d17d650085895af16e6df1f495eebf |
| summarize.py | b392f98081073fb05cd5fe7656e1f009599532068de2e715e93be7a308ee65b2 |
| engine.patch | bbcd34e0e8bea3d52bab63348ae8bbc8f4e1d6e3744eca6ca2e1b56712f5adf0 |
| containerd.patch | 6fc847e973005e7cb6a643f21cba7f8e94a78e5a694a855acef42506f4479acd |
| corrected-summary.json | 80d1c42b5b0112ae0f622c3ad914048efe83d733bc1805b95fc7fd3ef819f520 |
| initial-summary.json | 4e539113d54a0112257cd04e2eb75d8e732b014dacdb0e096083018c9b8c3093 |

Project: ripgrep 3fce3b5bb0236da2df6d99672afb8a719642eca7. Corrected cohort
`/tmp/dagger-rust-cold-image-ab-rdc0zgro`; report SHA256
df1546ad65a624db6b66e6cac9a244f948ba07266fd5a19fe3cab93c424190f4.
Raw stream-pairs-telemetry.jsonl: 21,434,841 bytes, SHA256
6f87b43790ef7102a46fe5a8f3c06d5be42318bde44b1a3b00b1f71dfadf393e.

Final supported test raw telemetry-live.jsonl SHA256
6272d99b857c55c0e01146554ed7910e0ad6b325611c811de198d9539b23ac47.
Exact inner stdout files (outer rendering copies excluded):

- final-snapshot-stdout-exact.log: f7a86e3cfc696908fd0c6fd59c303170b39b5b7aced73bb1d9d67efe9ebdae99
- final-large-stdout.log: c444b9c1f398252a57e14f974ea4ca250efb25a2d731a54387bc5c1ca9d6a719
- final-resolver-stdout.log: b8220e387cc33f1ddf727e19d76e7df6f5394e2a6b44cdd434607f18533f3efa

Old cohort: `/tmp/dagger-rust-cold-image-ab-8dg4m8of`, source/controller root
`/tmp/dagger-streamed-cold-engine.4JZ0SlL3`. Old raw telemetry SHA256
00e1e40f05de6ae130c331dd9f79b123cd614774f79a107649173cb64eb096be.
Failed large stage:
`/tmp/dagger-stream-large-correctness.p3eJvFR1/stages/large-race/engine-dev.log`,
SHA256 a2b3cb303af13945c22fc9900e4a4b5d098d8ccf9c744bbeff5e35e59b1ffd33.
These retained local records and published source artifacts preserve the work;
portable end-to-end packaging and broader workflow validation remain unfinished.
