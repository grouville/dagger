# Go collection contributions: verification and decisions

The original sixteen proposals now have **five open drafts, two closed PRs and nine performance proposals on hold**. The three newly opened fixes were reproduced on current upstream main before publication. Earlier source branches remain on the forks.

| Proposal | State | Evidence and decision |
| --- | --- | --- |
| [Share restored result lists, #14730](https://github.com/dagger/dagger/pull/14730) | Draft | A real captured cache exposed 394 million repeated lookup associations. Independent main fixtures improve large-list restore 713.15 → 49.53 ms and removal 31.43 s → 45.59 ms. Separate one-result lists restore about 2% slower; fresh insertion about 3% slower. Full-listing gain remains unmeasured. |
| [Skip unrelated directories in host globs, #14731](https://github.com/dagger/dagger/pull/14731) | Draft | Package lookup 9.28 → 0.10 ms; whole-tree control 14.13 → 14.12 ms. Thirteen added production lines preserve the existing matcher and ordering. No standalone listing gain claimed. |
| [Skip empty disk-usage bookkeeping, #14732](https://github.com/dagger/dagger/pull/14732) | Closed | The stress fixture and older experimental-cache results do not yet establish the payoff on a representative current-main command. Source and measurements remain available. |
| [Walk directly to a single include, #14733](https://github.com/dagger/dagger/pull/14733) | Closed | The larger fixture saves 2.46 ms per walk, the smaller about 8 µs. Actual benefit has not justified 77 added implementation lines and their filesystem edge cases. |
| [Keep copied schema types independent, #14736](https://github.com/dagger/dagger/pull/14736) | Draft | Two-line correctness fix. Both Install and Extend reproduce the overwrite on main c5456d9cbf and pass with the fix under the race detector. Extra allocation when an override would have reused spare array space; no new locks. |
| [Correct converted Dang list types, #14737](https://github.com/dagger/dagger/pull/14737) | Draft | One-line correctness fix. Four type/JSON cases fail on main c5456d9cbf and pass under the race detector. |
| [Preserve nested-selection item types, Dang #194](https://github.com/vito/dang/pull/194) | Draft | Valid program fails on main bf649b8d and passes with the fix; nullable cases stay rejected. The complete interpreter race suite passes. |

## Performance proposals on hold

- Scalar getters: fresh objects improve, but repeated reads regress 61.73 → 78.54 ms and allocate more.
- Argument preparation: fewer bytes allocated, but direct-input controls add an allocation and have mixed timing.
- Glob suffix filtering: matching paths cost about 1.6% more; construction cost and real-workload benefit still need assessment.
- Host config reads: fewer successful-read requests are proven, not an independent current-main command gain.
- Go generation matching: the sixteen-module main fixture improves in three of four pairs, with large variation. Representative workload and complexity review remain.
- Go native membership: the independent-main fixture is slower in most pairs.
- Dang typed methods and callback setup: both pass the full race suite on the newer bf649b8d main. Performance still needs measuring on that base.
- Dang error context: the patch no longer applies after upstream runtime changes. It needs a fresh review before its old performance evidence can be used.

## New discovery lead

The full upstream listing remains unresolved: the initial real-repository attempt hit 240 seconds without rows, and a diagnostic hit 900 seconds. These are failures, not timing wins. The faster earlier results used the combined experimental stack.

The completed discovery phase in the diagnostic spends about 260 seconds in roughly 700 pairs of Gomod.at and selected calls. A separate 726 subpath calls total about 173 seconds. Each small operation prepares another module invocation. These profile durations identify work to remove; they are not complete-command speedups.

A [small batching experiment](https://github.com/grouville/go/tree/experiment/go-collection-batched-selection) applies the existing selection rules to a package list in one call. Four behavior checks pass, including exclusions, normalization, duplicate/order preservation and binary building. Empty lists avoid a new module call. It is on the fork without a PR; the full-command benefit is not measured yet.

## Standard before opening

Establish a meaningful command gain, a substantial resource cost on real data, or a genuine correctness regression. Explain why the benefit justifies the code and risk. Keep slower controls and failed attempts. A faster microbenchmark alone is not sufficient.

Descriptions and commit messages lead with the concrete problem, a before/after example, the fix, its cost and the useful checks. Existing engines, volumes, telemetry and cache policies are preserved.

[Current-main checks and diagnostic evidence](experiments/standalone-go-collections/assessment/current-main-review/) · [Published branches](experiments/standalone-go-collections/published-branches.json) · [Earlier measurements](experiments/standalone-go-collections/assessment/)
