# Go collection performance: draft PR review queue

Current contribution assessment: **five drafts are open (#14730, #14731, #14736, #14737 and Dang #194); #14732 and #14733 are closed. Nine performance proposals remain on hold.** No further PR is being opened on a microbenchmark win alone. [Evidence and decisions](GO_COLLECTION_STANDALONE_REVIEW.md).

Outside this extraction queue, recovered [span indexing (#14738)](https://github.com/dagger/dagger/pull/14738) and [Go package-local search (Go #68)](https://github.com/dagger/go/pull/68) now also have drafts. Their fresh standalone measurements and held alternatives are in the [October 19 follow-up](experiments/standalone-go-collections/assessment/independent-followup-oct19/).

A separately reproduced [workspace-search correctness fix (#14740)](https://github.com/dagger/dagger/pull/14740) brings the reviewed queues to eight drafts. It follows the existing design for searching Dagger-created files. Go #68 remains blocked by a filename regression in its published version; the scoped replacement and its variable timing controls are recorded in the [scoped-search follow-up](experiments/standalone-go-collections/assessment/scoped-search-followup-oct19/).

This queue covers **eight engine/CLI performance proposals, three Dang interpreter proposals, two Go module proposals and three correctness fixes**. It excludes several larger prototypes behind the earlier full-listing gains. Their unfinished upstream preparation is tracked in the [overall reconciliation](GO_COLLECTION_STANDALONE_REVIEW.md#earlier-gains-and-unfinished-larger-changes); the five-draft count is not the status of the entire project.

Sixteen descriptions are prepared for review: **13 performance proposals and 3 correctness fixes**. All sixteen source branches are pushed, each one signed-off commit directly on its upstream main base. The [published branch manifest](experiments/standalone-go-collections/published-branches.json) links every clean source branch. This description branch remains separate.

The [standalone verification report](GO_COLLECTION_STANDALONE_REVIEW.md) is the current source of performance claims. Figures in the queue below are historical experiments unless that report confirms a fresh standalone result. Opening requires a separate assessment of actual benefit, complexity and correctness risk. Historical gains and synthetic speedups alone are insufficient.

The work comes from profiling the cost of listing Go test collections on the real dagger/dagger repository:

```sh
dagger check --module go --check test --list --all
```

The earlier experimental listing contains 4,398 ordered rows; the fresh upstream full-repository attempts did not complete. Component benchmarks, cache restart measurements and complete-command results are identified separately below. These are independent comparisons on different stages of the experimental stack; their gains cannot be added together.

## Performance proposals

| # | Draft description | Target | Main evidence | Remaining preparation |
| --- | --- | --- | --- | --- |
| 1 | [Share restored result lists (#14730)](https://github.com/dagger/dagger/pull/14730) | dagger/dagger | Fresh main comparison: import 713.15 → 49.53 ms; prune 31.43 s → 45.59 ms. No demonstrated listing gain. | One combined PR, including the removal follow-up; four faster pairs and the full DagQL race suite pass. |
| 2 | [Skip disk-usage sampling for empty values](PR_ENGINE_SKIP_EMPTY_USAGE_SAMPLING.md) | dagger/dagger | Listing: 49.10 → 45.40 s; retained-cache preparation: 5.12 → 3.22 s. | Use the scoped performance branch, not the later policy-preflight experiment. |
| 3 | [Read host module config before a redundant stat](PR_READ_CONFIG_BEFORE_STAT.md) | dagger/dagger | Test-edited listing: 7.04 → 6.69 s; config requests: 6,890 → 3,526. | Retain the full-core-suite environment failures in validation notes. |
| 4 | [Prune host globs by their directory prefix](PR_CLIENT_HOST_GLOB_PREFIX.md) | dagger/dagger | Fresh main: package glob **9.28 → 0.10 ms**; whole-tree control **14.13 → 14.12 ms**. | Four pairs and the client race suite; plain-language description and commit; draft #14731 opened. No standalone complete-listing claim. |
| 5 | [Reach literal imports without enumerating sibling directories](PR_FSUTIL_LITERAL_WALKS.md) | dagger/dagger | Listing: 55.81 → 52.03 s; visited entries: 5.58 million → 237,287. | Keep the populated-host caveat explicit. |
| 6 | [Read trivial scalar fields without another cache result](PR_ENGINE_TRIVIAL_SCALARS.md) | dagger/dagger | Listing: 40.49 → 39.20 s, all four pairs faster. | Retain repeated-read allocation and mixed CPU controls. |
| 7 | [Build argument definitions without copying input specs](PR_SCHEMA_ARGUMENT_ITERATION.md) | dagger/dagger | Test-edited listing: 6.76 → 6.58 s; about 204 MB median paired allocation saving. | Retain the extra allocation for direct Inputs calls above 15 arguments. |
| 8 | [Reject impossible suffixes before regexp matching](PR_GLOB_LITERAL_SUFFIX.md) | dagger/dagger | Test-edited listing: 6.93 → 6.69 s; 13 production lines. | Independent CLI optimization. |
| 9 | [Recognize typed methods during declaration classification](PR_DANG_COERCED_METHOD_HOISTING.md) | vito/dang | Historical test-edited listing: 14.31 → 12.71 s. | Current-main race checks and component measurements pass; complete-command gain remains unproven. Held. |
| 10 | [Read source-error context only when evaluation fails](PR_DANG_LAZY_ERROR_CONTEXT.md) | vito/dang | Historical test-edited listing: 12.88 → 11.51 s. | Patch no longer applies after the newer upstream runtime changes. Held. |
| 11 | [Reuse empty callers for concrete function callbacks](PR_DANG_CALLBACK_CALLER.md) | vito/dang | Historical test-edited listing: 10.01 → 9.53 s. | Current-main race checks and component measurements pass; complete-command gain remains unproven. Held. |
| 12 | [Share generation matching during package discovery](PR_GO_GENERATION_MATCHES.md) | dagger/go | Historical test-edited listing: 9.28 → 7.33 s. | Independent current-main fixture: 12.60 → 12.47 s, 2/4 pairs. Held. |
| 13 | [Use native membership for generation directories](PR_GO_NATIVE_MEMBERSHIP.md) | dagger/go | Historical test-edited listing: 7.63 → 7.44 s, 6/8 faster. | Independent main fixture regresses in most pairs. Held. |

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

Before opening a PR, establish its real-workload value and explain why that justifies its complexity and correctness risk. Mixed or unverified candidates stay on the forks. Fresh benchmarks preserve every attempt and use the same main source and fixtures on both sides, applying only that PR's production files to the candidate. The existing engines, volumes, telemetry settings and cache policies are preserved; the separate unchanged-main engine has completed the sixteen-module comparison and the current-main diagnostic is recorded in the verification report.

The [source inventory](experiments/go-collection-pr-preparation/source-inventory.json) records exact reviewed heads, bases, patch hashes and publication status. Historical validation belongs to those sources; it is not reported as a fresh test run on a future port.
