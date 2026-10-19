# Go collection contributions: verification and decisions

Sixteen independent source branches remain on the forks, each based directly on its pinned upstream main: Dagger `80699ac67a`, Go module `334136faaa`, or Dang `da1bed304c`. Four proposals were opened. Two remain drafts; two were closed after assessing whether their evidence justifies the complexity.

| Proposal | State | Evidence and decision |
| --- | --- | --- |
| [Share restored result lists, #14730](https://github.com/dagger/dagger/pull/14730) | Draft | A captured cache of 198,689 results implied 394 million repeated lookup associations. Main-only fixtures restore large shared lists in **713.15 → 49.53 ms** and prune in **31.43 s → 45.59 ms**. Separate single-result lists restore about **2% slower** and fresh insertion is about **3% slower**. A substantial scaling problem supports review; complete-listing gain remains unmeasured. |
| [Skip unrelated directories in host globs, #14731](https://github.com/dagger/dagger/pull/14731) | Draft | A package lookup improves **9.28 → 0.10 ms**; the whole-tree control is **14.13 → 14.12 ms**. The 13 added implementation lines retain the existing walk and matcher. This is a small change to repeated package discovery; no standalone complete-listing gain is claimed. |
| [Skip bookkeeping for values with no disk data, #14732](https://github.com/dagger/dagger/pull/14732) | Closed pending representative evidence | Main's 200,000-scalar stress fixture improves **998.88 → 459.68 ms**. An older experimental mixed cache of 854,567 results also improves **5.12 → 3.22 s**, but that does not establish the current-main target workload. The fresh 16-module cohort retained 6,581 results after completion; it is not a full-repository or peak-at-prune census. The 19-line patch remains on the fork until its actual payoff is established. |
| [Walk directly to a single include, #14733](https://github.com/dagger/dagger/pull/14733) | Closed pending justification | **2.51 ms → 49.87 µs** with 2,048 unrelated root entries; about **8 µs** saved with eight. The change adds 77 implementation lines preserving permissions, symlinks and callback behavior. Two older whole-command pairs on the experimental stack are insufficient to justify the current-main filesystem change. |

The PR comments record the assessments. Both closed source branches and all positive and negative measurements are preserved.

## Remaining proposals

No further PRs are being opened from this batch until their real benefit is weighed against implementation complexity and correctness risk.

- Scalar getters: fresh objects improve, but repeated reads regress **61.73 → 78.54 ms** and allocate more. Held.
- Argument preparation: fewer allocated bytes, but direct-input controls add an allocation and have mixed timing. Held pending a meaningful real-workload gain.
- Suffix filtering: nonmatching paths improve greatly, while matching paths cost about **1.6%** more in six longer pairs. Pattern construction cost and current-workload payoff still need assessment.
- Typed method classification: the SDK fixture improves, but it uses Dagger's pinned Dang v2.1.4 rather than measuring the target Dang main dependency. Held for further validation.
- Error-context and callback changes: standalone interpreter gains and cost controls exist. They need a contribution assessment before opening.
- Host config reads: the request-count test uses the unchanged main closure exposed through a test seam. It proves fewer successful-read requests, not an elapsed command gain.
- Go generation matching: on unchanged Dagger main and independent Go module main, the 16-module fixture improves **21.57 → 12.79 s** after ordinary-source edits and **14.37 → 12.07 s** after test-file edits. Each is faster in three of four pairs, with substantial run-to-run variation. Promising, but held for representative workload and complexity review.
- Go native membership: the same independent-main fixture regresses **18.77 → 24.38 s** after source edits and **13.95 → 16.26 s** after test edits. No PR is opened.
- Three correctness fixes reproduce failures on their current-main bases and pass with the fixes. They make no performance claim and remain separate proposals.

The seven selected Go checks and all 48 listing commands complete successfully on the unchanged-main engine. Warmups add and remove a real test; every observed name and row matches the expected list. The comparison includes fresh CLI startup, telemetry and cleanup. It does not measure the complete dagger/dagger repository.

The ten Dagger branches passed their scoped package race checks; the four Dang branches passed the interpreter race suite. Added result-list controls also pass with the race detector. No existing engine or volume was reset, restarted or removed.

## Standard before opening

Explain the actual problem, the repeated work, the change, the measured benefit and cost, and how to reproduce the checks. Apply the same standard to the commit message. Branch preparation details belong in the tracking report.

A faster microbenchmark alone does not qualify a performance contribution. Establish a meaningful command improvement, a substantial resource cost on real data, or a genuine correctness regression. Identify the fixture, baseline, cache state and limitations; keep all slower controls. Record why the benefit justifies the code and risk before opening. Close a proposal when that case is not established, while preserving the experiment on the fork.

[Published branches](experiments/standalone-go-collections/published-branches.json) · [Raw standalone results, current-main cohort, census and assessment comments](experiments/standalone-go-collections/assessment/) · [Descriptions and historical experiments](GO_COLLECTION_PR_SERIES.md)
