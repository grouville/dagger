# Historical prototype: Kyle's greetings-api workload

Measured September 24, 2026. On the same machine, the exact
`dagger check -l --all` command improved from **6.26 s to 3.83 s warm**
(**39% less elapsed time**, 1.64× speedup). Real source edits improved from
**7.16–9.63 s to 3.90–4.39 s**. The complete output stayed identical, and
six unchanged Go-module QA checks pass before and after.

**The 500 ms goal is not met, and a meaningful cold-start win is unproven.**
This measures an experimental combined stack,
not the performance of the unmodified collections branch or this checkout alone.
The collection CLI parsing and batch-description issues from the thread still
reproduce on both stacks.

## Same project, same command

The primary workload is [kpenfound/greetings-api, collections at
14d684f](https://github.com/kpenfound/greetings-api/tree/14d684fccf75a137de96f3f0c7eb8c6dafef2d3e):

```sh
cd greetings-api
time dagger check -l --all
```

Each timed run launches a new CLI process from the project directory and waits
for it to exit. The harness supplies only the selected CLI binary and engine.
It retains generation checks, all installed modules, the backend Go-test base,
and the frontend service wired into Playwright. No `--generated=false` or
Go-only selector is used for these listing measurements.

The expected output is all **14 rows** from Kyle's example: two SDK generation
checks, ESLint, three Go-module generation checks, six root Go tests,
golangci-lint, and Playwright. The ordered output, descriptions, and flags match
byte for byte across every warm sample and corresponding edit pair. The
[expected listing](collections-qa-performance-data/expected-checks.txt) is saved.
This command discovers checks; it does not execute all those checks.

Kyle reported **41.72 s real / 0.83 s user / 0.29 s sys**. His hardware,
engine state, cache state, and exact binaries are unknown. That is valuable
motivation, but it is **not the denominator for our speedup claim**. The pasted
thread otherwise reports correctness results, not measured performance gains.

## Before and after

The baseline is [dagger/dagger#14221](https://github.com/dagger/dagger/pull/14221)
at `175dca038268639231c21323cd7aaa1d746617dd`, freshly built without our
changes, using [dagger/go@collections](https://github.com/dagger/go/tree/9af8ac523f026932454474e06053d9eaf251d868)
at `9af8ac523f026932454474e06053d9eaf251d868`.

The optimized stack combines discovery/schema/CLI changes, the source-built Go
scanner changes, a Dang syntax-cache prototype, and existing PRs
[#14180](https://github.com/dagger/dagger/pull/14180),
[#14182](https://github.com/dagger/dagger/pull/14182),
[#14183](https://github.com/dagger/dagger/pull/14183), and
[#14179](https://github.com/dagger/dagger/pull/14179).
It includes neither the prebuilt scanner experiment nor the native-Git
telemetry experiment. The CLI uses the original Git metadata reader.

Five serial warm rounds rotate the order of the three variants. Each uses a
retained, running engine and populated content cache. Timings exclude profiling.

| Variant | Median | Observed range |
| --- | ---: | ---: |
| Original collections CLI + engine + Go module | **6.257 s** | 6.093–6.448 s |
| Optimized CLI + engine stack, original remote Go module | **4.024 s** | 3.898–7.818 s |
| Optimized CLI + engine stack + local optimized Go module | **3.825 s** | 3.636–3.898 s |

Most of this project's measured gain comes from the CLI/engine stack. The
additional module change saves about 0.20 s by these medians. That last comparison
also changes the module source from remote to local, so it does not isolate the
scanner algorithm alone. The engine-only outlier is retained. Five samples do
not establish a production p95.

### Edit a file, then immediately run the command

Each row below changes actual source, then immediately launches the same CLI
command without warming the edited input. The engine stays running. Each edit
starts from the original source; a unique comment prevents accidental reuse of
an earlier benchmark edit. Variant order alternates. These are single paired
observations, not medians.

| Operation | Original | Optimized | Verified output |
| --- | ---: | ---: | --- |
| Unchanged source | 6.416 s | 3.623 s | Original 14 rows |
| Comment-only edit in `main.go` | 7.519 s | 3.900 s | Same 14 rows |
| Rename `TestSelectGreeting` | 7.318 s | 4.061 s | New name present; old name absent |
| Add a test | 7.158 s | 4.060 s | Exactly 15 rows |
| Add a Go module with a test | 9.628 s | 4.387 s | Exactly 16 rows |
| Remove additions and restore source | 6.107 s | 3.782 s | Original 14 rows restored |

The oracle checks the full expected URI/flag set, rejects duplicates, and
compares complete ordered output between implementations. It therefore catches
stale names, missing rows, unexpected rows, and changed descriptions. All source
edits were restored. All twelve commands exceed the 500 ms budget.

### Cold engine cache

Each of these four commands used a new, empty engine-cache volume. The order was
original → optimized, then optimized → original. Both variants used local Go
module checkouts at the recorded versions, so the optimized variant did not
benefit from omitting a remote Go-module download that the baseline had to do.
All other application configuration remained intact. All four listings matched
the same complete 14-row output.

| Fresh engine cache | Original | Optimized |
| --- | ---: | ---: |
| Pair 1 | 66.289 s | 60.167 s |
| Pair 2, reverse order | 77.624 s | 77.198 s |

The second pair is nearly tied, and variation between rounds is larger than
the observed improvement. **These samples do not establish a reliable
cold-start speedup.** Cold work includes external dependency/image acquisition,
runtime setup, and compilation. The engine was ready before timing; installation
and engine startup are excluded. Host page caches and upstream caches were not
cleared. The dedicated engines were stopped after capture; their volumes were
retained. These cold fixtures use local Go sources on both sides, whereas the
warm baseline above uses the original remote reference.

Earlier first-use observations of 86.21 s original and 6.58 s optimized are
**not a valid cold comparison**: the optimized run followed another variant
that had already populated that engine's cache. The prebuilt-scanner results in
the research log also belong to a different, smaller workload.

## Correctness relative to Kyle's QA

The original `dagger/go@9af8ac5` GoDev assertions and fixtures were kept unchanged.
Only harness wiring was adapted to use our selected persistent engine instead
of building another engine, and the implementation under test was substituted.

| Original GoDev check | Original | Optimized |
| --- | --- | --- |
| `discovery-check` | Pass | Pass |
| `discovery-from-subdir-check` | Pass | Pass |
| `collection-check` | Pass | Pass |
| `tests-collection-check` | Pass | Pass |
| `module-introspection-check` | Pass | Pass |
| `skips-non-modules-check` | Pass | Pass |

These exercise collection get/list/subset ordering and validation, empty
selections, batch and individual test execution, skipped modules, nested modules,
test signatures, and build constraints. This is a selected relevant subset,
not a claim that Kyle's entire roughly 25-item matrix or greetings-api's entire
application test suite passed. QA runtimes are saved for diagnosis; they are not
used for a speedup claim because dependency warming was not matched.

The selected-test case was also exercised in the actual greetings-api checkout:

```sh
dagger check go/modules/tests/run --go-module=. \
  --go-test=TestSelectGreeting --go-test=TestFormatResponse
```

Both implementations report **two tests passed**. A separate wcprof capture on
each records exactly one `GoTests.subset`, one `GoTests.batch`, and one
`GoTests_Batch.run`, with no individual `GoTest.run` execution. Both captures have
zero dropped events and zero open operations. Batching already works at this
pinned baseline; it is not a new performance fix from our stack.

| Concern from the thread, checked on the current test path | Original | Optimized |
| --- | --- | --- |
| Selected tests execute through the batch | Pass | Pass |
| Listing describes the batch | Still says “Run this test.” | Same issue |
| Collection traversal through `api call` | Parsing failure below | Same failure |

Adding `-l` to that selected-test command prints one grouped command on both
stacks, but retains the item description. That reproduces Kyle's distinction
between grouping keys and explaining that a batch will run.

One of the thread's failures remains reproducible through the CLI:

```sh
dagger api call -m /path/to/go-module modules get --key . path
# load return type for function "list": typedef "[GoModule]" not found
# in currentTypeDefs(returnAllTypes: true)
```

Both original and optimized exit with this same error. Passing the module's
collection API checks does not prove that CLI argument parsing works. The old
thread's `go/modules/test` command also differs from the pinned module's current
`go/modules/tests/run` check surface; those must not be silently treated as the
same QA case.

## What wcprof says to optimize next

Separate warm captures have **zero dropped events and zero open operations**.
The capture's engine span excludes part of the CLI lifecycle, so unprofiled
process elapsed time remains the headline measurement.

| Recorded work | Original | Optimized |
| --- | ---: | ---: |
| Engine operations | 27,972 | 20,722 |
| Internal queries / schema-build calls | 250 | 220 |
| Total schema-build self-time | 268 ms | 17 ms |
| Three `GoModule.tests` calls, summed wall duration | 3.93 s | 314 ms |
| Two frontend `tsx` processes, summed duration | 4.71 s | 3.75 s |

**The next large measured target is frontend TypeScript registration during
module loading.** Both optimized executions invoke the generated frontend
entrypoint beneath `ModuleSource.asModule`. They overlap, taking 1.87 s and
1.88 s each. The profile does not establish how much is transpilation, imports,
registration queries, or telemetry shutdown. Instrument those boundaries before
choosing a fix. In particular, the 3.75 s sum is not 3.75 s of removable command
latency.

The same profile also records twelve `Query.git` executions with 2.45 s summed
self-time. This is engine module/source resolution, not proof that CLI telemetry
Git metadata accounts for that duration. Preserve lockfile resolution and
caller visibility when removing repeated work.

The PR links [#14283: eager file/service evaluation](https://github.com/dagger/dagger/issues/14283).
Keeping service construction and source selection lazy is relevant to this
project's settings and cold behavior. It remains separate from the observed
frontend registration cost; the profile does not justify assigning both to one
cause. Removing Playwright's service setting is not a valid optimization for
this benchmark.

## Complexity and Dagger caching

The implemented improvements reduce redundant work while retaining the UX:

- Schema path/prefix indexes replace repeated pairwise ancestor and alias scans.
- Request-local receiver sharing enumerates each distinct receiver once, rather
  than once for every leaf path using it. Workspace identity remains part of the
  request's memoization boundary.
- Bulk CLI metadata avoids publishing and querying one engine object per URI,
  description, and dimension field. Producing N output rows still requires at
  least O(N) work.
- One source snapshot scan builds Go test-name indexes and reuses parsed source.
  It removes the second ripgrep pass and the O(files × matches) join. The scanner
  exec remains keyed by immutable source content, helper source, flags, and
  normal Dagger inputs. Application edits invalidate the appropriate result.
- Prepared schemas reuse immutable work only within the same session authority
  and caller scope, with fresh mutable root/field ownership. The Dang syntax
  prototype reuses pristine parsed syntax, not an evaluated workspace answer.

There is no host-path cache of discovery answers, mutable global key list, or
cache-volume substitute for content-addressed results. Cross-session frontend
registration reuse needs an explicit design for immutable metadata versus
caller-owned objects; simply removing session/cache scopes would be unsafe.

Two remaining algorithmic opportunities should be kept in proportion. Go module
membership still uses O(candidates × modules) work. Replacing it with repeated
immutable `Map.with` calls would itself build the map quadratically. A bulk
constructor or native set/join can address that. A separate Dang `Map.merge`
prototype removes repeated copying, but this discovery path does not use it, so
none of the reported gain is attributed to that fix. Neither is evidence that
the current roughly two-second frontend registration can be solved with a
faster Go membership test.

## Reproduction and evidence

Host: Intel i5-9300H, eight logical CPUs, Linux x86-64, local Docker engines.
Baseline and optimized binaries are built before timing. The
[provenance record](collections-qa-performance-data/provenance.json) contains
immutable refs, binary digests, stack composition, and source locations. The
[lockfile](collections-qa-performance-data/dagger.lock) pins the other modules
and images. The optimized warm checkout's Git origin was a local clone path,
which emitted a telemetry URL warning; the original Git metadata implementation
was retained in both CLIs.

From either disposable app checkout, select the intended binary and engine:

```sh
python3 /path/to/dagger/hack/bench-artifact-discovery.py \
  --runs 5 --warmups 1 --output /tmp/greetings-measurement \
  -- /path/to/dagger-cli --engine container://selected-engine check -l --all
```

For a separate warm profile, add
`--wcprof-url http://127.0.0.1:ENGINE_DEBUG_PORT` before `--`. The runner initializes
and drains the recorder before measuring. For profiling a newly edited input or
an empty engine cache, use `--warmups 0 --cold-profile` and a fresh/drained
recorder; otherwise profile initialization would warm the workload.

[Warm samples](collections-qa-performance-data/warm-summary.json),
[edit samples](collections-qa-performance-data/edit-summary.json),
[cold samples](collections-qa-performance-data/cold-summary.json),
[original QA results](collections-qa-performance-data/module-qa-summary.json),
[selected-test batch results](collections-qa-performance-data/batch-qa-summary.json), and
[before](collections-qa-performance-data/wcprof-original.txt)/[after](collections-qa-performance-data/wcprof-full-stack.txt)
wcprof analyses accompany this report. The analyzer's cross-query critical-path
simulation does not model all CLI dependencies; its what-if table is not a
forecast of achievable end-to-end speedup. Concurrent durations overlap.

Raw stdout/stderr, wcprof recordings, and experiment drivers are retained under
`/tmp/collections-perf/greetings`. Copies of the warm/edit/cold/batch drivers
accompany the data; their paths and engine names record this lab setup and must
be adapted for another machine. The broader
[research log](bench-artifact-discovery.md) documents earlier synthetic workloads,
scaling tests, cache-boundary checks, and packaging prototypes. Its approximately
two-second synthetic timings are not timings for this full application.
