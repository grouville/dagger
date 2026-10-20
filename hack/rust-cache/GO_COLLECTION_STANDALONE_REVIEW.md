# Go collection contributions: verification and decisions

The original sixteen proposals now have **five open PRs, two closed PRs and nine performance proposals on hold**. The three correctness fixes were reproduced on current upstream main before publication. Earlier source branches remain on the forks. Two recovered proposals now also have drafts: [span indexing, #14738](https://github.com/dagger/dagger/pull/14738) and [Go package-local search, Go #68](https://github.com/dagger/go/pull/68). A separately reproduced [workspace-search correctness fix, #14740](https://github.com/dagger/dagger/pull/14740), brought the reviewed queues to eight open PRs. [Configuration declaration reuse, #14741](https://github.com/dagger/dagger/pull/14741), now brings the total to nine: seven drafts and two ready for review. Go #68 now contains the verified package-scoped replacement; it needs #14740 before merging to support package directories created through Dagger on host workspaces.

This is the status of the extracted PR queue, not the whole Go listing project. Its thirteen performance proposals comprise **eight engine/CLI changes, three Dang interpreter changes and two Go module changes**. The three correctness fixes are additional. Preparing and pushing a branch does not establish that its independent benefit justifies a PR.

Of the eight engine/CLI performance proposals, two are open drafts, two were closed and four remain on hold. Both Go module performance proposals remain on their fork branches without PRs: shared generation matching did not repeat its earlier gain in the new comparison; native membership regresses in most independent fixture pairs and does not currently qualify as a performance contribution.

## Current focus

Prepare and verify the larger changes behind the complete Go collection-listing gains. Prioritize ownership reuse, parallel discovery and configuration-declaration reuse, followed by bulk artifact metadata and batching module discovery. The counts of small PRs and correctness fixes do not establish that these end-to-end gains have reached upstream.

Verify each against an explicit upstream base, with a representative package/module ratio, complete edited-workspace commands, controls, resource costs and useful correctness checks. Preserve all attempts. A worthwhile complete-command gain can justify a patch even when a small fixture shows little benefit. Publish verified, scoped changes as draft PRs under the existing authorization; avoid starting unrelated small optimizations while this work remains unfinished.

## Earlier gains and unfinished larger changes

There is also an [older catalogue](upstream-prs/README.md), containing nineteen engine branches and a separate [Go package test-discovery proposal](upstream-prs/go-package-test-discovery.md). Two engine proposals overlap with this queue: empty disk-usage sampling and trivial scalar fields. The earlier catalogue includes scalar-array ownership/encoding, collection indexing, artifact output, SDK input batching and configuration-declaration reuse. Most have not been reassessed in the recent standalone review; their old descriptions must not be read as current approval to open PRs.

The roughly hundred-to-forty-second period included [parallel Go discovery](NATIVE_GO_PARALLEL_DISCOVERY.md), measured 88.65 → 67.11 s; [retained module ownership](NATIVE_GO_PACKAGE_MODULE_OWNERSHIP.md), 68.37 → 56.81 s; [span indexing](NATIVE_GO_WIDE_TRACE_INDEX.md), 53.58 → 46.72 s; and [configuration-declaration reuse](PR_ENGINE_CONFIG_DECLARATIONS.md), 45.51 → 40.65 s. These are separate controlled comparisons, not an additive waterfall or fresh current-main measurements. Their unpublished source remains available.

The earlier experimental stack successfully listed all 4,398 rows in roughly seven seconds after test-file edits and four seconds after ordinary-source edits, using fresh CLIs on warm engines. Those results remain recorded in the [complete project history](GO_COLLECTION_THREE_SECOND_PLAN.md). The recent bare-upstream timeouts below do not measure that stack or establish a regression of it. Cold results are a separate study on an older stack.

Several larger changes behind the earlier gains were not included in the sixteen-proposal extraction queue. Their upstream preparation is unfinished:

| Change | Earlier complete-command comparison | Current contribution assessment |
| --- | --- | --- |
| [Typed artifact metadata and immutable field projection](NATIVE_TYPED_ARTIFACT_METADATA.md) | Ordinary-source edit: 40.86 → 26.76 s | Substantial measured benefit; extends experimental engine/CLI APIs. Needs standalone extraction, API review and validation on the intended upstream base. |
| [Batch Go module paths and selection facts](NATIVE_GO_BATCHED_DISCOVERY_FACTS.md) | Ordinary-source edit: 25.45 → 19.21 s | Useful measured benefit; the fork commit depends on an earlier ownership prototype. Standalone port and ownership/selection checks remain. |
| [Retain indexed package-owner facts](NATIVE_GO_INDEXED_OWNER_FACTS.md) | Test-file edit: 11.47 → 9.56 s | The gain removes full-owner lists introduced by our unpublished prototype. Upstream main does not carry those lists, so this is not a directly applicable standalone improvement. |
| [Reuse prepared schema metadata](NATIVE_DANG_PREPARED_SCHEMA.md) | Test-file edit: 11.92 → 10.86 s | Extends private declaration reuse. Sharing boundaries, initialization and client isolation need review before this can qualify as an upstream contribution. |

These are separate controlled comparisons on different stages of the development stack, not additive savings or current-main measurements. They remain candidates, not contributions that have already passed the standalone quality bar. Earlier reviewed performance work is already merged, including [#14383](https://github.com/dagger/dagger/pull/14383), [#14384](https://github.com/dagger/dagger/pull/14384), [#14375](https://github.com/dagger/dagger/pull/14375) and [#14179](https://github.com/dagger/dagger/pull/14179); those are separate from this queue.

## Recovered standalone reviews, October 19

[Raw samples, checks, source patches and wcprof reports](experiments/standalone-go-collections/assessment/independent-followup-oct19/) now cover the two new drafts and the proposals held after fresh verification.

| Change | Fresh evidence | Decision |
| --- | --- | --- |
| [Span indexing, #14738](https://github.com/dagger/dagger/pull/14738) | Current-main fresh index, 4,096 children: 25.64 → 2.05 ms, 6/6 pairs; unchanged allocations. Full clientdb races pass. A real earlier listing recorded over two billion comparisons. | Draft. Small change reuses existing maps without adding locks or state. Earlier full-listing gain is disclosed as an experimental-engine comparison; the new small-command cohort establishes no end-to-end gain. |
| [Go package-local search, Go #68](https://github.com/dagger/go/pull/68) | Shared-workspace, complete listing across 16 packages: 7.94 → 6.16 s, 5/6 pairs; allocations 6.42 → 4.59 GB. Identical-code control: 8.248 → 8.252 s over six pairs. One-package controls are close to flat. | Draft source updated to `bc0d99e`, directly on Go main. Preserves literal filenames, symlink traversal, mounts, Unicode and filename order. Needs engine #14740 for newly created host-workspace package directories. Full dagger/dagger still hits the 240-second cutoff. See the [crossover verification](experiments/standalone-go-collections/assessment/package-search-crossover-oct19/). |
| [Workspace search of Dagger-created paths, #14740](https://github.com/dagger/dagger/pull/14740) | Real-CLI regression: three scoped searches fail on main and pass with the fix; unrelated missing paths still error. Original design and existing tests explicitly include Dagger-created files. | Draft correctness fix, no speed claim. Preserves host search and client scoping; uses existing workspace state. Required by the scoped Go replacement when a package directory exists only through Dagger edits. |
| [Reuse unchanged configuration declarations, #14741](https://github.com/dagger/dagger/pull/14741) | Bounded LRU restored, source/tests identical to the verified LRU commit. Current-main component: 324.928 → 3.989 µs, 2,818 → 3 allocations; distinct inputs cost 4.7% more. Full workspace race suites pass. | Draft. Earlier warm optimized-engine full listing: 45.51 → 40.65 s, 4/4 faster. New current-main main/LRU/DagQL attempts all time out at 180 s without rows; no completed-command gain or LRU-over-DagQL win established. [Comparison and limits](experiments/standalone-go-collections/assessment/config-cache-full-listing-oct19/). |
| Parallel module discovery | Fixed-configuration comparison: 19.35 → 14.27 s, 3/4 pairs. CPU rises 42.65 → 52.78 CPU-seconds and allocation 6.09 → 6.73 GB. | Held. The earlier 14.85 → 7.32 s screen is not the confirmed headline. Run-order-dependent work and resource cost need another control before publication. |
| Batch main-package selection | 16 main packages: 10.52 → 10.78 s, 2/4 pairs, with more CPU and allocations. | Held. Behavior checks pass, but this cohort does not justify a performance PR. |
| Retain module ownership | Earlier full listing: 68.37 → 56.81 s. Expanded current-main study uses 64 packages across eight modules, unique test edits and matched stock engines. Output and cleanup pass. wcprof confirms 64 module searches become one layout check. | Held for measurement diagnosis. Identical-code controls also show large timing differences. Separate consecutive profiles execute all 64 package getters, then hit all 64, then execute all 64 again. The cause is not established. No new latency claim or PR; earlier behavior tests still pass. [Controls and diagnostic evidence](experiments/standalone-go-collections/assessment/ownership-controls-oct19/). |

These are separate warm-engine workloads, not additive savings. The one-package and many-package fixtures have the same test count but different search costs: the published Go change starts one search per test file. All timed commands start a new CLI, edit source and tests, validate ordered rows, and include successful cleanup. Normal telemetry and cache policies stay enabled. A same-code control measures 15.72 → 15.71 s over two pairs; individual observations remain variable and are retained.

The older collection-index benchmark uses 1,000 independent collection field definitions, not 1,000 collection keys. The official Go module has only a few such definitions. That stress result alone does not establish a useful listing improvement.

## Extracted PR queue

| Proposal | State | Evidence and decision |
| --- | --- | --- |
| [Share restored result lists, #14730](https://github.com/dagger/dagger/pull/14730) | Draft | A real captured cache exposed 394 million repeated lookup associations. Independent main fixtures improve large-list restore 713.15 → 49.53 ms and removal 31.43 s → 45.59 ms. Separate one-result lists restore about 2% slower; fresh insertion about 3% slower. Full-listing gain remains unmeasured. |
| [Skip unrelated directories in host globs, #14731](https://github.com/dagger/dagger/pull/14731) | Draft | Package lookup 9.28 → 0.10 ms; whole-tree control 14.13 → 14.12 ms. Thirteen added production lines preserve the existing matcher and ordering. No standalone listing gain claimed. |
| [Skip empty disk-usage bookkeeping, #14732](https://github.com/dagger/dagger/pull/14732) | Closed | The stress fixture and older experimental-cache results do not yet establish the payoff on a representative current-main command. Source and measurements remain available. |
| [Walk directly to a single include, #14733](https://github.com/dagger/dagger/pull/14733) | Closed | The larger fixture saves 2.46 ms per walk, the smaller about 8 µs. Actual benefit has not justified 77 added implementation lines and their filesystem edge cases. |
| [Keep copied schema types independent, #14736](https://github.com/dagger/dagger/pull/14736) | Ready for review | Two-line correctness fix. Both Install and Extend reproduce the overwrite on main c5456d9cbf and pass with the fix under the race detector. Extra allocation when an override would have reused spare array space; no new locks. |
| [Correct converted Dang list types, #14737](https://github.com/dagger/dagger/pull/14737) | Ready for review | One-line correctness fix. Four type/JSON cases fail on main c5456d9cbf and pass under the race detector. |
| [Preserve nested-selection item types, Dang #194](https://github.com/vito/dang/pull/194) | Draft | Valid program fails on main bf649b8d and passes with the fix; nullable cases stay rejected. The complete interpreter race suite passes. |

## Performance proposals on hold

- Scalar getters: fresh objects improve, but repeated reads regress 61.73 → 78.54 ms and allocate more.
- Argument preparation: fewer bytes allocated, but direct-input controls add an allocation and have mixed timing.
- Glob suffix filtering: matching paths cost about 1.6% more; construction cost and real-workload benefit still need assessment.
- Host config reads: fewer successful-read requests are proven, not an independent current-main command gain.
- Go generation matching: the fresh sixteen-module fixture is 12.60 → 12.47 s, faster in two of four pairs. Its earlier gain did not repeat.
- Go native membership: the independent-main fixture is slower in most pairs.
- Dang typed methods and callback setup: current-main race checks and component benchmarks pass. Matched complete-command measurements remain too variable to establish a reliable gain. The typed-method negative check asserts an optimization invariant, not a user-visible correctness regression.
- Dang error context: the patch no longer applies after upstream runtime changes. It needs a fresh review before its old performance evidence can be used.

## New discovery lead

The full upstream listing remains unresolved: the initial real-repository attempt hit 240 seconds without rows, and a diagnostic hit 900 seconds. These are failures, not timing wins. The faster earlier results used the combined experimental stack.

The standalone package-scoped Go replacement also hits 240 seconds without rows on the real repository. Its complete small-fixture gain is confirmed, but it does not resolve the earlier discovery stage. The current checkout's independently derived inventory has 4,483 rows with the added test; this is an expectation, not a successful listing. A separate experiment now batches module test selection using the canonical rules; it has no performance claim or PR yet. Combining it with package-scoped search and the root-module path identity case also reaches 240 seconds with no rows. The [failed full-repository attempt](experiments/standalone-go-collections/assessment/combined-discovery-oct19/) is retained; it establishes no gain.

The completed discovery phase in the diagnostic spends about 260 seconds in roughly 700 pairs of Gomod.at and selected calls. A separate 726 subpath calls total about 173 seconds. Each small operation prepares another module invocation. These profile durations identify work to remove; they are not complete-command speedups.

A [small batching experiment](https://github.com/grouville/go/tree/experiment/go-collection-batched-selection) applies the existing selection rules to a package list in one call. Four behavior checks pass, including exclusions, normalization, duplicate/order preservation and binary building. Empty lists avoid a new module call. It is on the fork without a PR. The fresh 16-main-package command comparison is 10.52 → 10.78 s, faster in 2/4 pairs; no full-repository benefit is established.

## Standard before opening

Establish a meaningful command gain, a substantial resource cost on real data, or a genuine correctness regression. Explain why the benefit justifies the code and risk. Keep slower controls and failed attempts. A faster microbenchmark alone is not sufficient.

Descriptions and commit messages lead with the concrete problem, a before/after example, the fix, its cost and the useful checks. Existing engines, volumes, telemetry and cache policies are preserved.

[Current-main checks and diagnostic evidence](experiments/standalone-go-collections/assessment/current-main-review/) · [Published branches](experiments/standalone-go-collections/published-branches.json) · [Earlier measurements](experiments/standalone-go-collections/assessment/)
