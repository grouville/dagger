# Share generation matching during Go package discovery

The selected module change improves complete listing on real dagger/dagger after both kinds of edit:

| Workload | Before | Local sharing | Faster pairs |
| --- | ---: | ---: | ---: |
| Test-file edit | 9.28 s | 7.33 s | 4/4 |
| Ordinary-source edit | 5.91 s | 4.16 s | 4/4 |

These are fresh CLI processes on the same warm development engine, with real source edits, normal telemetry, ordinary GC, output, final flushing and successful session cleanup. Both versions complete adding and removing a test before four alternating measured pairs per workload. All 24 real-repository commands return the same ordered 4,398 rows. These cohorts are separate from earlier comparisons; their gains are not additive. Current cold performance and Rust latency are not measured.

Source: [Go fork commit 511d381](https://github.com/grouville/go/commit/511d38145daf87b531e44ed9b1c3b641fbe89ba3). This is a follow-up to the indexed-owner-facts prototype, based on `de633b12ed2aa02e42adb698a23fcecc13faf36d`. It is not an independently validated port onto current upstream main. No PR is open. The [review description](PR_GO_GENERATION_MATCHES.md) is prepared for approval.

## Find the actual reduction

The CPU profile attributed substantial work to Dang's generic `List.reduce`. Replacing three insertion-sort helpers with the development engine's native string sorter produced only small, variable complete-command differences: test edits **8.60 → 8.31 s**, ordinary edits **5.69 → 5.60 s**. That screen stays unselected and its separate cohort is retained.

A separate diagnostic engine then labeled reductions by the source location of their authored block. Its interpreter race suite passes. First-use and warm captures return all rows without lost events. In the warm capture, **8.19 of 20.85 sampled CPU-seconds** belong to `GoModule.matchingGenerateDirectories`, at baseline `go.dang:738`. Sorting accounts for only a small part of the reduction work. These instrumented captures locate work; they are not latency comparisons.

Package discovery includes packages with generation commands as well as tests and binaries. For each of 80 modules, generation selection transformed the same workspace-wide Go-file glob into directory names. The engine shared the glob operation, but its result still crossed the SDK boundary and went through the interpreted filter/map for each module.

## Keep the calculation in the existing pipeline

`Go.packages` now prepares immutable generation matches once, after finding eligible modules. Each transient package-discovery object uses those matches when selecting its own generation directories. Standalone module generation constructs its own matches from its workspace and settings.

The original glob/filter/map algorithm is unchanged. Every module still discovers generation directives and applies its include and exclude rules. The helper contains only arrays and a boolean; it is local to discovery and is not stored in collection results. The `GoPackages` and `GoPackage` classes are byte-for-byte unchanged. There is no new engine API, language builtin, global cache or lock. Production code grows by 33 lines, mostly to represent the shared value and pass it through private methods.

Profiles retain **804 evaluations, all 800 getters and 799 unchanged discovery hits** after a test edit. SDK requests fall **1,494 → 1,415**. Ordinary-source profiles retain all getter and test-discovery hits, with three evaluations and **572 → 493 SDK requests**. The 79 removed requests are repeated preparation, not skipped authored getters.

| Engine work | Test edit, before → after | Ordinary edit, before → after |
| --- | ---: | ---: |
| CPU-seconds | 45.64 → 31.10 | 25.17 → 11.05 |
| Allocated bytes, decimal GB | 9.57 → 6.47 | 5.15 → 2.07 |

## Check the smaller cases too

An initial version shared the calculation through a new `gomod` API. It improved the large repository, but increased SDK requests and slowed every measured small-repository pair: **0.592 → 0.693 s** for one module and **0.669 → 0.950 s** for sixteen. It stays unselected.

Local sharing removes those additional requests. One module is essentially flat at **0.567 → 0.569 s**, with allocation **183.9 → 185.2 MB**. Sixteen-module results are mixed: the first four-pair cohort has medians **0.696 → 0.673 s**, but only one faster pair. A separate fixed eight-pair follow-up has medians **0.768 → 0.695 s**, five faster pairs and a 23 ms median paired saving. Both cohorts remain in the evidence. They do not establish a dependable small-repository latency gain or an absence of outliers.

Twenty-five existing check invocations pass, covering discovery, ownership, selected tests, binaries, generation, globs, exclusions and cwd behavior. The added discovery regression passes both baseline and candidate. It checks nested modules, removed generation files, independent tool settings, exclusions and restoration of an earlier workspace. All 68 commands in the final timing protocols succeed. The helper's state is read-only during parallel discovery; its lifetime does not cross invocations.

## Remaining cost and evidence

The selected test-edit profile places **1.77 s** on the critical path in session lifecycle locking and **0.81 s** in result publication. The source-only profile places roughly **0.94 s** in interpreted evaluation, **0.52 s** in configuration stat operations and **0.51 s** in publication. Attribute those operations and their lock holders next. These diagnostic path segments are not additional measured savings.

[Evidence](experiments/go-generation-discovery/) retains all variants, attempts, source trees and patches, component/race results, raw timings and fourteen lossless captures. The benchmark engine is unchanged; the source-label wrapper runs in a separate diagnostic engine. All nine engines and cache volumes are retained, workspaces are restored, and capture switches are disabled. The dedicated diagnostic engine retains its labeling environment setting. Current stock-engine performance, cold listing and Rust latency remain separate work.
