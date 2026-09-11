# Completed stable-root generator comparison

Run `/tmp/dagger-rust-generator-pair-aly1heoz` completed 30 measured triples per
scenario on the same CLI and before/candidate engines documented in
[provenance](results.md#provenance). The frozen module is unchanged. The harness
SHA256 is `fe08a74e70b60b4e16b0eb1361e11b059b9dda7e9bf6a97d006ba63491c83985`;
it creates and verifies its own module Git root before any Dagger/Docker work.
This is a separate run, not a repair or continuation of the failed attempt.

**The change makes this Dagger fixture faster, not faster than native Cargo.**
Remaining paired overhead is +1152.251 ms application / +1437.164 ms library.
The first-use, faster-than-native cache-hit and near-native edit-loop goals
remain unmet.

## Complete process timings

[Raw timing CSV](stable-root-30pair-timings.csv) retains all 186 timed processes:
180 measured plus six warmup processes. No outliers or rejected-profile timings
are discarded. One setup build per side and one warmup triple per scenario are
excluded from statistics. Times are milliseconds, measured around complete
standalone processes; no listener or persistent CLI session is used.

| Scenario / side | Median | Mean | p95 | Full range |
| --- | ---: | ---: | ---: | ---: |
| Application, before | 1942.182 | 1957.774 | 2092.673 | 1822.296–2140.257 |
| Application, candidate | 1304.898 | 1297.295 | 1405.219 | 1161.606–1466.008 |
| Application, native | 143.869 | 149.790 | 176.615 | 135.230–184.316 |
| Library, before | 3139.915 | 3149.217 | 3451.503 | 2942.449–3451.701 |
| Library, candidate | 1635.090 | 1636.997 | 1802.279 | 1478.041–1851.051 |
| Library, native | 184.064 | 186.864 | 205.993 | 173.385–211.651 |

| Paired statistic (n=30/scenario) | Application | Library |
| --- | ---: | ---: |
| Saving median | 649.438 ms | 1521.509 ms |
| Saving mean | 660.479 ms | 1512.220 ms |
| Saving p95 | 832.368 ms | 1830.243 ms |
| Saving full range | 420.055–922.733 ms | 1091.398–1895.923 ms |
| Candidate faster | 30/30 | 30/30 |
| Candidate minus native median | +1152.251 ms | +1437.164 ms |
| Candidate minus native p95 | +1264.650 ms | +1616.323 ms |
| Candidate/native ratio median | 8.820x slower | 8.665x slower |

Differences and ratios are calculated per paired sample, not by subtracting
separate medians. p95 uses nearest rank `sorted[ceil(.95*n)-1]`, the 29th sorted
observation at n=30. Every execution order occurs five times per measured
scenario, and savings remain positive in all groups:

| Order (n=5 each) | Application saving median ms | Library saving median ms |
| --- | ---: | ---: |
| before / after / native | 655.710 | 1383.587 |
| before / native / after | 696.744 | 1501.202 |
| after / before / native | 636.921 | 1647.336 |
| after / native / before | 671.938 | 1535.042 |
| native / before / after | 593.216 | 1590.646 |
| native / after / before | 615.673 | 1407.063 |

Before/candidate warmups were 2208.125/1416.597 ms application and
3173.446/1383.871 ms library. They are not cold samples.

## wcprof completeness, actual execution and attribution

[Trace audit CSV](stable-root-30pair-trace-audit.csv) retains all 124 timed Dagger
roots and 124 separate post-timer `build-messages` roots, including warmups,
root/process residuals, gate status and observed actual-exec duration. Each
command matches exactly one completed CLI root inside its recorded process
boundary. After root selection, every record is selected by the whole trace ID,
not a time cut. Full local trace/gate evidence uses the prefix
`/tmp/dagger-rust-single-generator-30pairs-stable-root-analysis-`.

- **119/124 timed gates pass; five remain rejected.** All 124 observe exactly
  one successful rsync + Cargo build + Cargo metadata process inside the timer.
  That exact count is fully supported for the 119 accepted traces; for the
  other five, unseen work cannot be excluded.
- **124/124 diagnostic gates pass, with zero additional execution.** Retrieval
  of Cargo JSON is not treated as independent execution proof.
- No open operations, dropped links, orphans, cycles, unresolved waits or
  scheduling conflicts are reported. Observed replay drift is -0.2% to -0.0%.
  Small drift does not override a missing completeness marker.

These five measured library traces lack `wcprof.session_complete`:

| Label | Trace ID | Process ms |
| --- | --- | ---: |
| library-6-after | b0e8d8d116a91b1bdddd898a535f5c19 | 1709.434 |
| library-7-after | 4c073d9562b7afeb2988e8a7ebc6de0b | 1747.119 |
| library-14-after | 20b87e42996c0c38ac27eda9606d358e | 1645.140 |
| library-21-before | a6156ffa35e74431797d07280847bf86 | 3208.685 |
| library-27-after | b955f0cd304765493b94710ed84ab096 | 1595.012 |

One exact-ID late scan finds byte-identical records and no marker for each;
all five late gates still reject. Original and late gates are preserved, with
nanosecond root/last-span timestamps in local `-late-completeness.json`. No
carrier is borrowed or synthesized. This occurs on both engines; do not assign
the telemetry-lifecycle issue to the generator fix without further evidence.

All timed commands have 30 POST query spans on both engines. Observed operation
counts are 472→463 application and 532→523 library. One actual
`Changeset.withChangesets` call disappears; user compilation is not skipped.
Accepted class self-time medians:

| Component | Application before→candidate ms (n=30/30) | Library before→candidate ms (n=29/26) |
| --- | ---: | ---: |
| Changeset.withChangesets | 677.6→absent | 1530.0→absent |
| Changeset.diffStats | 30.1→30.8 | 191.8→193.7 |
| ModuleSource.asModule | 120.6→120.8 | 120.1→119.0 |
| Rust.build residual | 135.8→138.1 | 131.9→133.0 |
| Previous target transfer | 20.7→20.8 | 128.6→135.4 |
| Artifact host download | 13.5→14.2 | 77.7→77.8 |

Rejected traces are excluded only from causal rankings, hence the unequal
library attribution counts. Observed Cargo-action medians across all n=30
samples are 250.112→251.382 ms application and 266.012→269.829 ms library,
including the five incompletely gated observations. There is no compiler-speed
claim. The removed merge matches the large process saving; metadata-history
differences below still limit assigning every saved millisecond to that call.

Candidate startup/session steps remain roughly 39–46 ms each, query self time
73/77 ms, and aggregate artifact checksum self time roughly 165/191 ms in
accepted application/library profiles. Process medians also include 27.9/28.2
ms before the CLI root and 13.3/10.9 ms afterward. `consuming /v1/traces` denotes
SSE establishment/lifecycle, not a measured telemetry flush bucket. These are
measured costs to investigate, not additive promises of future savings.

## Correctness, source identity and limitations

All 62 unique edits, including warmups, reproduce their recorded source hashes.
All 186 Cargo JSON outputs agree on selection/freshness. Application edits dirty
only `prototype-app`; library edits dirty exactly `prototype_library`,
`prototype-app`, `prototype-secondary`. Timed actual stderr names the matching
compiling packages. Unrelated source/lockfiles, current source manifests and
the outside-subtree sentinel remain correct.

All **248 executable comparisons are raw-byte equal**. All **248 archive
comparisons are raw-byte unequal**, but pass the strict fixture-only
compiler-member-name equivalence described in the [README](README.md#correctness-and-measurement-caveats).
Ordered members, ordinary object bytes, index, headers and padding remain exact
after only the permitted full-name mapping in memory; rlib link metadata may
refer to that same member. Raw hashes are retained and no artifact is rewritten.
All 372 recorded executable behavior checks match the current edit. Latest
retained output files were independently rehashed against the manifest.

Candidate artifact/ancestor modes match native. All 217 recorded permission
differences are the recognized baseline 755→777 or 644→666 defect; no unknown
discrepancy is accepted. Each side keeps its own output metadata history, so
this is not a byte-and-metadata-identical paired state experiment.

Every trace imports the owned module directory; all 1488 observed namespace
entries remain `mod(rust.)`, with cache-volume lookup hits and 62 distinct
actual build-action digests per engine. No `/tmp` context import or diagnostic
reexecution from the failed run recurs. This preserves normal module isolation,
not a global cache namespace. The setup Git-root verification and observed
trace identity are separate evidence, not a claim of a Git probe on every call.

Source review: a single regular **no-op retains equal full Before/After
snapshots minus root `.git`**; it does not substitute empty directories. This
run does not benchmark no-op results. The preexisting metadata-only `isEmpty`
limitation, multi-generator metadata handling and the known nested-cwd failure
remain unresolved; see [correctness limits](results.md#correctness-tests-and-unresolved-properties).

The same CLI, pinned image, default dev/full debug profile and flags are used.
Both Dagger engines already exist and use `cleanup=false`; readiness remains
`asymmetric-or-unknown`. Both emit live local OTel with DO_NOT_TRACK=1. Native
is ordinary Cargo via `docker exec` with persistent intermediates/final outputs,
not host Cargo, and does not perform Dagger's metadata/selection/export workflow
or run wcprof. This is one Linux/amd64 two-package fixture, not evidence for
cold/onboarding, exact-cache hits, dependency version upgrades, remote engines,
macOS or general Cargo project support. Native cleanup verifies its exact ID
and owner label; no shared engine/cache/image/volume is pruned.

Maintained analyzer executable SHA256:
`de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba`.
Raw OTel extraction SHA256:
`6bcfc89f1f29029423e402d211b1ee26107585b06d7c7ec9e7bedc67c764135b`.
Full local audit: `/tmp/dagger-rust-single-generator-30pairs-stable-root-analysis-report.md`,
`-evidence.json`, `-summary.json`, `-order-statistics.json` and per-command raw
gates/traces. Only benchmark source, public measurements and summaries are
included here; no maintained/private analyzer source is copied.
