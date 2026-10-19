# Go collection performance: draft PR review queue

Sixteen descriptions are prepared for review: **13 performance proposals and 3 correctness fixes**. All sixteen source branches are pushed, each one signed-off commit directly on its upstream main base. The [published branch manifest](experiments/standalone-go-collections/published-branches.json) links every clean source branch. This description branch remains separate.

The [standalone verification report](GO_COLLECTION_STANDALONE_REVIEW.md) is the current source of performance claims. Figures in the queue below are historical experiments unless that report confirms a fresh standalone result. Draft PRs are authorized once the individual improvement and its scope are supported; an old combined-stack win is not sufficient.

The work comes from profiling the cost of listing Go test collections on the real dagger/dagger repository:

```sh
dagger check --module go --check test --list --all
```

The measured listing contains 4,398 ordered rows. Component benchmarks, cache restart measurements and complete-command results are identified separately below. These are independent comparisons on different stages of the experimental stack; their gains cannot be added together.

## Performance proposals

| # | Draft description | Target | Main evidence | Remaining preparation |
| --- | --- | --- | --- | --- |
| 1 | [Avoid quadratic restored-cache indexing](PR_ENGINE_SHARE_RESTORED_POSTINGS.md) | dagger/dagger | Fresh main comparison: import 713.15 → 49.53 ms; prune 31.43 s → 45.59 ms. No demonstrated listing gain. | One combined PR, including the removal follow-up; four faster pairs and the full DagQL race suite pass. |
| 2 | [Skip disk-usage sampling for empty values](PR_ENGINE_SKIP_EMPTY_USAGE_SAMPLING.md) | dagger/dagger | Listing: 49.10 → 45.40 s; retained-cache preparation: 5.12 → 3.22 s. | Use the scoped performance branch, not the later policy-preflight experiment. |
| 3 | [Read host module config before a redundant stat](PR_READ_CONFIG_BEFORE_STAT.md) | dagger/dagger | Test-edited listing: 7.04 → 6.69 s; config requests: 6,890 → 3,526. | Retain the full-core-suite environment failures in validation notes. |
| 4 | [Prune host globs by their directory prefix](PR_CLIENT_HOST_GLOB_PREFIX.md) | dagger/dagger | Listing: 58.10 → 53.76 s, both pairs faster. | Keep the two-pair evidence limit explicit. |
| 5 | [Reach literal imports without enumerating sibling directories](PR_FSUTIL_LITERAL_WALKS.md) | dagger/dagger | Listing: 55.81 → 52.03 s; visited entries: 5.58 million → 237,287. | Keep the populated-host caveat explicit. |
| 6 | [Read trivial scalar fields without another cache result](PR_ENGINE_TRIVIAL_SCALARS.md) | dagger/dagger | Listing: 40.49 → 39.20 s, all four pairs faster. | Retain repeated-read allocation and mixed CPU controls. |
| 7 | [Build argument definitions without copying input specs](PR_SCHEMA_ARGUMENT_ITERATION.md) | dagger/dagger | Test-edited listing: 6.76 → 6.58 s; about 204 MB median paired allocation saving. | Retain the extra allocation for direct Inputs calls above 15 arguments. |
| 8 | [Reject impossible suffixes before regexp matching](PR_GLOB_LITERAL_SUFFIX.md) | dagger/dagger | Test-edited listing: 6.93 → 6.69 s; 13 production lines. | Independent CLI optimization. |
| 9 | [Recognize typed methods during declaration classification](PR_DANG_COERCED_METHOD_HOISTING.md) | vito/dang | Historical test-edited listing: 14.31 → 12.71 s. | Clean branch pushed; full upstream interpreter race suite passes; standalone timings pending. |
| 10 | [Read source-error context only when evaluation fails](PR_DANG_LAZY_ERROR_CONTEXT.md) | vito/dang | Historical test-edited listing: 12.88 → 11.51 s. | Clean branch pushed; full upstream interpreter race suite passes; standalone timings pending. |
| 11 | [Reuse empty callers for concrete function callbacks](PR_DANG_CALLBACK_CALLER.md) | vito/dang | Historical test-edited listing: 10.01 → 9.53 s. | Clean branch pushed; full upstream interpreter race suite passes; standalone timings pending. |
| 12 | [Share generation matching during package discovery](PR_GO_GENERATION_MATCHES.md) | dagger/go | Historical test-edited listing: 9.28 → 7.33 s. | Independent upstream-main port pushed; 11 checks pass. Main-engine comparison pending. |
| 13 | [Use native membership for generation directories](PR_GO_NATIVE_MEMBERSHIP.md) | dagger/go | Historical test-edited listing: 7.63 → 7.44 s, 6/8 faster. | Independent two-line upstream-main port pushed; 10 checks pass. Main-engine comparison pending. |

The two restored-membership descriptions are counted as **one** proposal. The [older removal description](PR_ENGINE_REMOVE_RESTORED_POSTINGS.md) is retained for traceability, not as another PR.

## Correctness fixes

| # | Draft description | Target | Regression and scope |
| --- | --- | --- | --- |
| 14 | [Isolate field override histories across class forks](PR_CLASS_FORK_HISTORY_ISOLATION.md) | dagger/dagger | Parent/fork overrides overwrite each other through shared slice capacity. Two production lines; Install and Extend regressions fail without the fix. |
| 15 | [Preserve element types when restoring lists](PR_DANG_LIST_ELEMENT_TYPES.md) | dagger/dagger | Restored lists acquire another list wrapper in their type. One production line; four cases fail without the fix. |
| 16 | [Preserve non-null elements in nested list selections](PR_DANG_NESTED_SELECTION_ELEMENTS.md) | vito/dang | A valid nested selection is rejected. Six-line inference change; complete-program regression and nullable negative cases. |

These fixes were found along the Go collection investigation. None claims a speedup. They can be reviewed independently of the larger performance prototypes.

## Measurement and review conventions

The descriptions follow the structure of Guillaume's reviewed and merged performance PRs: [#14383](https://github.com/dagger/dagger/pull/14383), [#14384](https://github.com/dagger/dagger/pull/14384), [#14375](https://github.com/dagger/dagger/pull/14375) and [#14179](https://github.com/dagger/dagger/pull/14179). Those reviews approved scoped changes with concrete measurements and explicit compatibility boundaries. Their approval does not cover this new series.

Each description explains the repeated work, the change in work performed, the relevant before/after results, meaningful regression coverage and the cost or limitation. Complete-command comparisons use fresh CLI processes and real edits on warm engines, including telemetry and successful session cleanup. Profiling is separate from timing. Cold starts, current released Dagger and Rust latency improvements are not established by those comparisons.

Published percentage reductions are calculated from the displayed column medians. A median paired saving is named separately when available. Slower controls and mixed workloads remain in the descriptions or their linked evidence.

The ten clean dagger/dagger branches pass their package race checks on main `80699ac67a`. Both Go changes are independently ported onto module main `334136faaa`, with 21 targeted checks passing on the retained diagnostic engine. The four clean Dang branches pass the full interpreter race suite on main `da1bed304c` and are pushed to the newly created grouville/dang fork. Every branch is one commit on its own upstream main; none contains the other performance proposals.

Before opening a PR, confirm its standalone result and the complexity/performance tradeoff. Mixed or unverified candidates stay on the forks. Fresh benchmarks preserve every attempt and use the same main source and fixtures on both sides, applying only that PR's production files to the candidate. The existing engines, volumes, telemetry settings and cache policies are preserved; a separate unchanged-main engine is planned for the module comparison.

The [source inventory](experiments/go-collection-pr-preparation/source-inventory.json) records exact reviewed heads, bases, patch hashes and publication status. Historical validation belongs to those sources; it is not reported as a fresh test run on a future port.
