# Go collection improvements: standalone verification

Every source branch is one signed-off commit directly on its repository's pinned main: Dagger `80699ac67a`, Go module `334136faaa`, or Dang `da1bed304c`. All sixteen branches are pushed to Guillaume's forks. Historical measurements on the combined experimental stack are separate from the results below.

| Change | Standalone result | Verification status |
| --- | --- | --- |
| [Shared result lists (#14730)](https://github.com/dagger/dagger/pull/14730) | Import 2,049 results: **713.15 → 49.53 ms**; prune 8,192 roots: **31.43 s → 45.59 ms**. All four pairs faster. | Main plus only this PR; full DagQL race suite passes. Cost controls: separate-list import **39.75 → 40.53 ms**; fresh insertion **38.57 → 39.81 ms**, six pairs. Complete-listing gain unmeasured. |

| [Skip unrelated host directories (#14731)](https://github.com/dagger/dagger/pull/14731) | Package pattern: **9.28 → 0.10 ms**; module pattern: **10.01 → 0.60 ms**; whole-tree control: **14.13 → 14.12 ms**. | Four pairs; full client race suite. Description and commit explain the prefix checks and the control. Draft #14731 opened. |

| [Skip bookkeeping for values with no disk data](PR_ENGINE_SKIP_EMPTY_USAGE_SAMPLING.md) | Cleanup preparation: **998.88 → 459.68 ms**, **158.94 → 91.12 MB** allocated. | Four pairs. Provider controls show mixed small timing changes and unchanged allocation counts; race suite and both provider transitions covered. |
| [Avoid listing unrelated directories for one include](PR_FSUTIL_LITERAL_WALKS.md) | With 2,048 root siblings: **2.51 ms → 49.87 µs**; eight siblings: **59.17 → 51.27 µs**. | Four pairs. Wildcard fallback control retained; tests compare entries, metadata, ordering, symlinks, permission and callback errors. |

The remaining standalone cohorts and additional tradeoff controls are running. No unverified cumulative figure is used as a standalone result. Draft PRs are opened only after the individual result and its scope justify them.

The [review queue](GO_COLLECTION_PR_SERIES.md) contains the proposed descriptions. Source publication is recorded in [the branch manifest](experiments/standalone-go-collections/published-branches.json).

Each proposed PR and commit message must explain the user-visible context, the repeated work, the change, the measured benefit and cost, and how to reproduce the checks. Metadata about branch preparation belongs in this report, not in the PR narrative. Measure the workload that cannot benefit as well as the one that does; retain slower results.
