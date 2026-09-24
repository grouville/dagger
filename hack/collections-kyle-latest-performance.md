# Discovery with Kyle's scanner-free listing

Start with the [normal-engine audit](collections-normal-mode-performance.md)
and [branch instructions](collections-performance-start.md) for the latest
reference. The historical measurements below used `--extra-debug` engines.

Follow-up: the [next investigation](collections-next-performance.md) measures
the full experimental candidate at 3.016 s against a fresh matched 6.465 s
baseline, isolates the TypeScript loader cost, and records new cold failures.
The comparisons below are the earlier measurements, without that SDK change.

Measured September 24, 2026, following Kyle's report of **29.88 s cold and
3–4 s warm**. His earlier 41.72 s and latest 29.88 s differ by 28.4%; those are
his observations, not controlled samples from this host. He attributes the
major saving to removing the Go helper build from artifact listing.

The engine PR still points to `175dca038268639231c21323cd7aaa1d746617dd`, and
`greetings-api` still points to `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`.
The Go module advanced from `9af8ac523f` to
`1784ff37eb3dd1aacab7aaff91b1d86e311cc8de` ("dont use go-include unless we have to").

**Every variant below uses Kyle's new Go module unchanged.** Our scanner/index
patch is not part of this comparison. All variants use the same app checkout,
local module source, locked dependencies, and exact `dagger check -l --all`
command, including CLI exit. Only the selected CLI/engine differs. Broken SSH
agent forwarding is omitted on all sides. Timings are serial and unprofiled;
profiles are collected afterward. All builds finish before measurements.

## Warm results

Five rounds alternate forward/reverse variant order after warmup.

| Variant | Median | Range | Reduction vs original |
| --- | ---: | ---: | ---: |
| Original collections engine/CLI | **6.731 s** | 6.346–6.943 s | 0.0% |
| Committed engine/CLI changes | **4.997 s** | 4.790–5.754 s | 25.8% |
| Committed changes + experimental syntax cache | **3.981 s** | 3.806–4.105 s | 40.9% |

The incremental syntax-cache comparison here is 4.997 s to 3.981 s, or 20.3%.
The cache is still experimental; these are not all production commits.
Do not compare the original's 6.73 s here with Kyle's 3–4 s as a regression:
hardware, engine history, and other environment conditions are not controlled
across our machines. The 500 ms target remains unmet.

## Real edits

One sequence uses new source content without warming the edited input. Order
alternates between variants. The optimized column includes the syntax cache.

| Edit | Original engine/CLI | Optimized + syntax cache |
| --- | ---: | ---: |
| unchanged | 6.418 s | 4.081 s |
| comment-edit | 7.170 s | 4.004 s |
| rename-test | 6.986 s | 4.217 s |
| add-test | 7.215 s | 4.157 s |
| add-module | 8.241 s | 4.226 s |
| restore | 6.436 s | 3.903 s |

Every complete listing matches in content, order, and description: 14 normal
rows, 15 after adding a test, 16 after adding a module. Expected key sets are
checked independently of the baseline output. Sources are restored afterward.
This lists checks; it does not execute the full application test suite.

## Cold result and limits

Two fresh engine-cache volumes give **77.052 s original / 82.266 s optimized
with syntax cache**. There is no demonstrated cold improvement in this pair.
Engines are already ready at the start; host and upstream caches remain.
The original also logged failed background OAuth refreshes. We retain the
whole-command times and do not subtract unprofiled suspected overhead.

Kyle's "cold" cache boundaries were not specified in enough detail to match
our fully empty engine volumes. His 29.88 s remains a separate observation.
The old four-sample cold matrix used the previous Go module and cannot support
a cold-performance claim for this new comparison.

## Why the changes still help

The CLI still benefits from one listing session and bulk metadata. The engine
still benefits from indexed dimensions, request-local receiver sharing, less
module/schema setup, and the existing shutdown/loading fixes. Dang still
benefits from avoiding repeated parsing. These changes apply even when the Go
module's listing does not execute a helper.

The [isolated syntax-cache report](collections-syntax-cache-performance.md)
explains ownership, complexity, tests, and upstream limitations. Focused Dang
and collections tests passed for that exact experimental engine before this
matrix. This matrix additionally verifies listing invalidation with the new
module; it does not claim a new full integration-suite run on Kyle's module.

## Next opportunities, not measured fixes

* `GoMod.isGoModule` sorts all owned Go files merely to check whether any exist.
  Existence checking can avoid that sort while keeping `ownFiles` ordering.
* `ownFiles` uses insertion sort: O(F²) comparisons/copies for F files. A native
  immutable list sort could reduce this to O(F log F). The workspace glob's
  directory traversal order cannot simply substitute for full byte-path order.
* `testNames` filters all M search matches for each of F files: O(F × M).
  Grouping once needs a bulk-built index; repeated immutable-map insertion would
  introduce another quadratic construction cost.
* TypeScript registration still starts fresh Node processes. Import/transpile
  work remains a target. No TypeScript optimization is included here.
* For actual checks, distribute a static helper in a small multi-architecture
  OCI image pinned by digest, retaining normal Dagger input/result caching.
  Our earlier 3.9 MB linux/amd64 snapshot prototype establishes feasibility;
  published-artifact transfer latency and other architectures are not measured.
  Keep the helper out of listing. The current helper checks Go syntax with
  `go/parser`; it does not prove type correctness or successful compilation.

The [raw evidence](collections-qa-performance-data/kyle-latest/) includes every
sample, the benchmark driver, source pins, complete configuration, and separate
wcprof analyses. No code from these speculative opportunities is included in
this earlier comparison.
