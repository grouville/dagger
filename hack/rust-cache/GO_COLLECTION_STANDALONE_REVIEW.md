# Go collection improvements: standalone verification

Every source branch is one signed-off commit directly on its repository's pinned main: Dagger `80699ac67a`, Go module `334136faaa`, or Dang `da1bed304c`. All sixteen branches are pushed to Guillaume's forks. Historical measurements on the combined experimental stack are separate from the results below.

| Change | Standalone result | Verification status |
| --- | --- | --- |
| [Restored cache indexing](PR_ENGINE_SHARE_RESTORED_POSTINGS.md) | Import 2,049 results: **713.15 → 49.53 ms**; prune 8,192 roots: **31.43 s → 45.59 ms**. All four pairs faster. | Main plus only this PR; full DagQL race suite passes. Complete-listing gain unmeasured. |

The remaining standalone cohorts are running. No unverified cumulative figure is used as a standalone result. Draft PRs are opened only after the individual result and its scope justify them.

The [review queue](GO_COLLECTION_PR_SERIES.md) contains the proposed descriptions. Source publication is recorded in [the branch manifest](experiments/standalone-go-collections/published-branches.json).
