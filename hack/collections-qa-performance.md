# Collections discovery: committed changes on greetings-api

**Baseline update:** Kyle subsequently reported **29.88 s cold and 3–4 s warm**.
Go module `1784ff37eb` removes the helper build from artifact listing; the engine
and application refs are unchanged. The measurements below use the earlier Go
module (`9af8ac523f`) and must not be presented as gains over his new version.
His cold improvement and our warm improvement are separate comparisons.
The [new matched comparison](collections-kyle-latest-performance.md) uses his
new module on all sides: **6.73 s → 5.00 s** with committed engine/CLI changes,
then **3.98 s** with the experimental syntax cache. Its cold pair shows no gain.

Measured September 24, 2026. The exact `dagger check -l --all` workload now
measures **6.16 s → 4.40 s warm median (29% less elapsed time)**
using the committed changes. Real edits take **4.93–5.24 s**, down from
**6.97–7.54 s**. Every complete listing matches, including invalidated inputs.
**The 500 ms target is not met.**

These numbers replace the earlier **3.83 s prototype** as the result to quote
for the committed branch. That prototype included an experimental Dang syntax
cache. It is preserved in the [historical report](collections-qa-performance-prototype.md);
its measurements must not be presented as results of these commits.

A subsequent [isolated syntax-cache experiment](collections-syntax-cache-performance.md)
reproduces **4.52 s → 3.66 s** with only that prototype added to the committed
stack. It also records two edit sequences and an empty-cache pair. The cache
remains experimental and is not enabled by the committed production source.

## What was committed

Dagger branch: `perf/collections-discovery`. Engine/CLI code was built at
`6e6bdfb16a`; benchmark tooling was committed afterward as `a8ee0d74ae` and does
not change those binaries. No `go.mod` replacement, build overlay, or experimental
syntax cache is used. The normal dependency remains Dang **v2.1.4**.

| New Dagger commit | Change |
| --- | --- |
| `4fc6cdc44f` | Index dimension paths/aliases; share collection receivers within a request |
| `ee89fcb3e1` | Bulk listing metadata and one CLI discovery session |
| `9ed7c86a02` | Buffer table output so large listings retain every row |
| `1fe5cbcc20` | Avoid default lookup when the module environment is empty |
| `8f2c2d49b0` | Skip registration-only Dang metadata passes during native calls |
| `b184a54f01` | Avoid installing self-call modules twice |
| `80b042420f` | Reuse prepared schemas within the same caller/session authority |

The branch also cherry-picks the original commits from existing PRs
[#14180](https://github.com/dagger/dagger/pull/14180),
[#14182](https://github.com/dagger/dagger/pull/14182),
[#14183](https://github.com/dagger/dagger/pull/14183), and
[#14179](https://github.com/dagger/dagger/pull/14179), preserving authorship and
source commit references. These cover nested-client shutdown, empty Cloud metric
uploads, lazy schema digests, and direct module-config/environment reads.
The speedup is for their combination with the new changes, not an isolated
attribution to each commit.

Two related changes live in their respective repositories:

| Repository / branch | Commit | Included in this benchmark? |
| --- | --- | --- |
| dagger/go / `perf/scanner-index` | `c84f15b11981bdc2eb52987d4e6139c4309bfd82` | Yes: source-built scanner |
| Dang / `perf/collections-map-merge` | `d7fadb86cb93a0225fe6e3e699e995fd49cfede6` | No: independent library change |

These are local commits prepared for upstream review, not merged changes.
Nothing has been pushed. The Go and Dang commits are unsigned because their
configured SSH signing agent was unavailable; global signing configuration was
not changed. The experimental AST reflection clone, native-Git telemetry
rewrite, prebuilt scanner, and TypeScript timing instrumentation are excluded.
Schema reuse still warrants careful maintainer review of ownership and cache
boundaries; targeted tests are not a substitute for the full CI suite.

## What replaced the scan plus ripgrep path?

This is **reuse of an existing read and removal of orchestration**, not a claim
that a Go parser or regular expression is intrinsically faster than ripgrep.

Previously the module ran its include scanner, obtained test directories,
globbed each directory, searched test files through `Workspace.search`/ripgrep,
retrieved match metadata, and filtered all matches for each file. That last
join is O(files × matches), in addition to repeated API/runtime work.

The committed scanner walks one immutable directory snapshot with
`filepath.WalkDir`, groups files by their nearest module, and reads source for
its existing directive analysis. `go/parser` extracts comment directives;
`golang.org/x/mod/modfile` parses module files. A compatibility regular expression
extracts test names **from those already-read bytes**. It writes `.testnames`
alongside the existing scan outputs. Parsed directives and errors are reused
inside that scanner process when several module include graphs reach the same
source. Test names are ordered and deduplicated locally.

The regex deliberately preserves the old discovery rules, including single-line
signatures and listing tests regardless of build tags. Using AST function
names indiscriminately would change that behavior. The module does not run
`go test` or compile application tests to discover their names.

Dagger still keys the scanner exec by source content, helper source, flags, and
its normal container inputs. There is no host-path answer cache, mtime shortcut,
persistent collection-key cache, or cache-volume database of discovery results.
The static schema indexes and request-local receiver sharing likewise retain
workspace identity. Prepared schema reuse checks caller identity plus an opaque
session authority and preserves fresh mutable ownership.

## Workload and baseline

Project: [kpenfound/greetings-api at 14d684f](https://github.com/kpenfound/greetings-api/tree/14d684fccf75a137de96f3f0c7eb8c6dafef2d3e).
Baseline: [collections PR #14221](https://github.com/dagger/dagger/pull/14221),
Dagger `175dca038268639231c21323cd7aaa1d746617dd`, with
Go module `9af8ac523f026932454474e06053d9eaf251d868`.

```sh
cd greetings-api
time dagger check -l --all
```

Every measurement starts a fresh CLI from the project directory and includes
process shutdown. The harness supplies the intended binary and engine, with no
Go-only selector and no `--generated=false`. All SDKs, generation checks, lint,
backend Go-test base, and Playwright frontend-service configuration are retained.
The [expected output](collections-qa-performance-data/expected-checks.txt) contains
Kyle's complete 14 rows. Listing discovers checks; it does not execute the full
application test suite.

Both sides use the same Linux x86-64 host, Intel i5-9300H, eight logical CPUs.
All builds finish before timing; correctness suites run afterward. The broken
SSH agent was omitted for both variants; the workload's dependencies are public
and pinned. Both disposable checkouts have normal Git object stores and the
same GitHub origin. CLI Git telemetry enrichment remains enabled.

## Warm and edit results

Five serial warm rounds rotate three variants after each has been warmed.
Profiles are collected separately. Every sample has identical ordered output.

| Variant | Median | Observed range |
| --- | ---: | ---: |
| Original collections branch | **6.163 s** | 5.901–6.774 s |
| Committed engine/CLI, original remote Go module | **4.812 s** | 4.629–5.218 s |
| Committed engine/CLI + committed local Go module | **4.401 s** | 4.330–6.880 s |

The candidate's **6.88 s outlier is retained**. Its tail is not solved, and five
samples do not establish a production p95. The engine-only comparison keeps the
original remote Go module. Adding the optimized module also switches it to a
local checkout, so that increment does not isolate the scanner algorithm alone.

Each edit below is immediately followed by the same command, with no warmup of
that input. Each starts from original source and uses a unique marker. Variant
order alternates; results are individual observations, not distributions.

| Operation | Original | Committed | Expected rows |
| --- | ---: | ---: | ---: |
| Unchanged | 5.918 s | 4.368 s | 14 |
| Comment-only edit | 6.971 s | 4.936 s | 14 |
| Rename a test | 7.112 s | 5.024 s | 14 |
| Add a test | 7.402 s | 4.926 s | 15 |
| Add a module with a test | 7.535 s | 5.237 s | 16 |
| Restore source | 6.188 s | 4.440 s | 14 |

The oracle checks exact expected URI/flag sets, rejects duplicates, compares
complete output ordering/descriptions between variants, and verifies removed
names disappear. Sources are restored afterward. Every sample exceeds 500 ms.

## Cold cache and Kyle's 41.72 seconds

Each command below uses a new, empty engine-cache volume. Both Go module sources
are local in this comparison, to avoid giving the candidate an advantage from
skipping a remote module download. Other dependencies remain pinned and remote.

| New engine cache | Original | Committed |
| --- | ---: | ---: |
| Pair 1 | 66.066 s | 49.795 s |
| Pair 2 (reverse order) | 107.804 s | 72.045 s |

Both paired observations improve, but the variation between rounds is large
and there are only two observations per variant. Retain both pairs; do not
extrapolate a reliable cold-start percentage from these samples. The engine was
already ready when timing began; installation/startup, cleared host page caches,
and cleared upstream caches are not included.

**Our committed cold observations, 49.79–72.05 s, are numerically slower than
Kyle's reported 41.72 s.** We do not know whether his command used an empty engine
cache, his hardware, or his exact binaries. Therefore neither a speedup over
Kyle's observation nor a regression caused by our changes is established. Our
controlled baseline is the original branch measured on this same host.

## Correctness and remaining issues

All targeted validation on the committed build passes:

- Focused core/schema/CLI/telemetry tests and the scanner's two build modes.
- Race checks for receiver sharing and prepared-schema reuse.
- Eight collection integration groups, including all three 4,096-row formats.
- Six Dang groups covering directives, self-calls, workspace arguments, syntax
  versions, client attachable isolation, and explicit forcing/cache policy.
- The six unchanged GoDev checks on both original and committed implementations.
- Both selected greetings-api tests on both implementations; wcprof records one
  subset, one batch, and one batch run, with no individual test-run calls.

[Validation results](collections-qa-performance-data/committed/validation-summary.json)
and [batch evidence](collections-qa-performance-data/committed/batch-qa-summary.json)
are retained. This was targeted validation, not the complete repository CI.

The independent module QA retains the original GoDev assertions and fixtures.
Only harness wiring and the implementation under test differ. It covers
`discovery-check`, `discovery-from-subdir-check`, `collection-check`,
`tests-collection-check`, `module-introspection-check`, and
`skips-non-modules-check`.

The selected real-app probe runs `TestSelectGreeting` and `TestFormatResponse`
through `go/modules/tests/run` with two `--go-test` flags. Batching is checked
with wcprof, rather than inferred from grouped output. Its run timings are not
used as a performance claim because dependency warming is unmatched.

Two existing issues from Kyle's thread still reproduce on the committed build:
the grouped listing says “Run this test.” and `api call … modules get` fails
resolving `[GoModule]`. The performance changes do not fix either. This is not a claim that Kyle's whole roughly 25-item QA matrix
or the entire application's checks pass.

## Profiles and next opportunities

Separate wcprof captures have no dropped events or open operations:

| Work per captured listing | Original | Committed |
| --- | ---: | ---: |
| Engine operations | 27,936 | 20,699 |
| Internal queries | 250 | 220 |
| Schema build, summed wall duration | 328 ms | 34 ms |
| Three `GoModule.tests` calls, summed wall duration | 3.84 s | 0.96 s |

These durations overlap and are not additive command latency. The analyzer's
cross-query what-if table is not an end-to-end speedup forecast.

TypeScript frontend startup and Dang parsing remain substantial. The committed
capture has two overlapping `tsx` executions of about 2.27 s each and 2.07 s
summed across 19 Dang source evaluations. A separate disposable instrumentation
experiment, using the historical prototype engine, measured 1.36–1.44 s between
bootstrap and completed imports, roughly 40 ms for registration, and roughly
2 ms for connection shutdown. This includes import/transpilation work and does
not isolate SDK imports from application imports. It is diagnostic evidence,
not a new committed optimization or a directly comparable latency sample.

The next substantial candidates are a supported immutable-syntax API in Dang
and cheaper TypeScript imports/runtime preparation, cached through ordinary
Dagger inputs. Reusing caller-owned evaluated objects across sessions is not an
acceptable shortcut. Preserving lazy file/service construction, tracked in
[#14283](https://github.com/dagger/dagger/issues/14283), is also relevant to
this full application's cold path. Prebuilt helpers need a separately measured
production distribution path before claiming a full-application cold win.

The independent map merge commit changes repeated copying from O(NM + M²) to
expected O(N + M), preserving order and input immutability. It does not fix
repeated `Map.with` construction and this Go discovery path does not use it;
none of this benchmark's gain is attributed to it.

## Evidence and reproduction

[Build/commit manifest](collections-qa-performance-data/committed/manifest.json),
[warm samples](collections-qa-performance-data/committed/warm-summary.json),
[edit samples](collections-qa-performance-data/committed/edit-summary.json),
[cold samples](collections-qa-performance-data/committed/cold-summary.json),
[before](collections-qa-performance-data/committed/wcprof-original.txt)/[after](collections-qa-performance-data/committed/wcprof-candidate.txt)
profiles, and the [TypeScript diagnostic](collections-qa-performance-data/committed/ts-registration-diagnostic.json)
are saved with the report. The data directory includes the exact lab drivers;
their paths and engine names must be adapted on another machine. Raw recordings
and logs are retained in `/tmp/collections-perf/committed`.

From the app checkout, using the desired committed CLI and matching engine:

```sh
python3 /path/to/dagger/hack/bench-artifact-discovery.py \
  --runs 5 --warmups 1 --output /tmp/greetings-measurement \
  -- /path/to/dagger-cli --engine container://selected-engine check -l --all
```

For separate warm profiling, add `--wcprof-url http://127.0.0.1:DEBUG_PORT` before
`--`. For a fresh/drained recorder on cold or edited input, use `--warmups 0
--cold-profile` to avoid warming the input during recorder initialization.
The [research log](bench-artifact-discovery.md) preserves earlier scaling tests
and experiments; synthetic two-second timings do not describe this full app.
