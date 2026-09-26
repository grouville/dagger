# Keep pending file producers out of metadata-only discovery

A ready destination container caused `Container.withFile` to evaluate a pending
source file immediately. On greetings-api, that file is the backend executable:
an ordinary source edit followed by `dagger check -l --all` unnecessarily ran an
approximately eight-second `go build`.

The fix uses the existing `ContainerWithFileLazy` operation whenever **either**
the destination or the source has pending evaluation. In three alternating
pairs with previously unseen source contents, local edit-to-list completion
improves **9.806 → 1.602 s**. A test rename followed by listing improves
**9.898 → 1.599 s**. The profiler confirms that listing no longer executes that
build. Actual checks still build the executable when they consume it.

These are increments over the retained experimental SDK stack, not comparisons
with upstream main or Kyle's machine. The implementation itself is independent
of those SDK prototypes and applies to every caller of `Container.withFile`.
The 500 ms target remains unmet.

Normal-source commits:

* [`31f9ff0a19`](https://github.com/grouville/dagger/commit/31f9ff0a19): retain pending file producers through metadata-only copies.
* [`f3e8882a6a`](https://github.com/grouville/dagger/commit/f3e8882a6a): reuse interface signatures within one reconciliation pass.

## Change and cache semantics

The resolver already reads destination metadata for path expansion and ownership.
It then loads the source reference and clones the destination. Previously it
selected the lazy copy operation only when the destination was pending; a cached,
ready destination therefore forced a new source producer. The new condition is:

```go
if parentPendingLazy || dagql.HasPendingLazyEvaluation(file) {
    // Construct the existing ContainerWithFileLazy operation.
}
```

The cache-aware predicate includes restored/in-flight lazy state. The operation
already retains both dependency results, persists their references, and separates
metadata from filesystem demand. The actual copy still uses the original copy,
permission and owner implementation. Ready source plus ready destination keeps
its existing fast path. No new cache, cross-session schema reuse, skipped source
input or application-specific special case is added.

This is particularly useful for an edit after the destination image has become
warm. It does not accelerate the compiler, and it does not establish an additional
cold-start gain: the destination can already take the lazy path on first use.

## Matched local results

Fresh CLI process through blocking `waitpid`, with Cloud/OTLP export disabled.
The engines differ only by the source-pending condition. Five alternating pairs
for warm flows; three for each edit flow. Each new edit has a unique nonce, the
same bytes are used on both engines, and direct execution uses different bytes
from the preceding listing. Profiling is excluded from these samples.

| Operation | Before | After | Pairs |
| --- | ---: | ---: | ---: |
| Warm expanded listing | 1.607 s | 1.577 s | 5 |
| Warm filtered listing | 2.019 s | 2.043 s | 5 |
| Warm selected test | 1.677 s | 1.537 s | 5 |
| New main-file comment → expanded listing | 9.806 s | 1.602 s | 3 |
| Rename test → expanded listing | 9.898 s | 1.599 s | 3 |
| Different new main-file comment → selected test | 10.963 s | 11.040 s | 3 |

The reliable result here is removal of producer execution from discovery. Warm
differences are small/mixed; the consuming check's edit cost remains. Individual
rename samples reach 12.217 s before and 2.235 s after; retain the samples rather
than promising a fixed duration.

## Production Cloud and the remaining exit cost

The same CLI and engines also ran through ordinary Cloud authentication and
`https://api.dagger.cloud`. No local receiver or asynchronous relay is used here.
One core auth control, two setup listings, three warm pairs, three fresh-edit
pairs and one direct edited-check pair account for 17 commands.

| Operation | Before | After | Pairs |
| --- | ---: | ---: | ---: |
| Warm expanded listing, first series | 1.940 s | 2.432 s | 3 |
| New main-file comment → expanded listing | 10.294 s | 2.371 s | 3 |
| Different main-file comment → selected test | 11.147 s | 11.748 s | 1 |

The edit gain survives production export, but the warm Cloud result is slower.
An additional five-pair series gives **2.313 → 2.743 s** in separate medians;
its median paired delta is **+114 ms**. Keep both statistics: the baseline has
a 3.916 s sample and the distributions are variable. These data do not justify
a warm-speedup or blanket no-regression claim.

A separate Cloud profile pair takes 2.230 / 2.633 s. Recorded engine work spans
1.394 / 1.389 s, with 248 queries and six execs on each side. The uninstrumented
interval from the final engine operation to CLI exit is **701 / 1,079 ms**;
that interval explains 378 ms of the 403 ms difference. The profiles do not
contain exporter/shutdown spans, so this localizes the gap without proving
whether queueing, network, ingestion or another shutdown step caused it. The
next measurement should instrument that handoff, preserving trace delivery.

All 29 Cloud commands in these two trials validate their expected output. With
the seven previously authorized receiver-comparison commands, 36 of the existing
220-command allowance have been used. Listing does not normally print a Cloud
trace link; the explicit core auth control verifies the normal login path.

## Causal profile and correctness

Separate fresh-edit wcprof captures show:

| Profiled command | CLI before / after | Go build before / after |
| --- | ---: | ---: |
| Expanded listing | 9.944 / 1.777 s | 7.901 s / absent |
| Selected test | 11.008 / 11.342 s | 7.997 / 8.499 s |

All four captures have zero open/dropped operations and fit inside their CLI
intervals. The previous force followed `Container.withFile → Directory.file →
Directory.withFile → Container.file → Container.withExec → go build`. Nested
durations overlap; do not add them. Earlier wcprof simulator predictions drifted
substantially, so these claims use actual intervals and paired command timing.

Listings retain all 14 expected checks. Renamed tests appear and the old names
disappear. Actual selected checks succeed. A stricter HTTP test changes the
original missing-URL skip into a failure and verifies a fresh revision header
added to the backend handlers, proving that the edited binary actually runs.
Clearing only `GREETINGS_API_URL` produces the expected test failure.

The original negative control removed the entire configured base. That changed
the compiler environment and failed earlier because `gcc` was absent. It is
retained as an unaccepted control, not counted as the expected HTTP failure.
The local trial therefore attempted 64 commands: 63 validated outcomes and one
unaccepted control. Four validated commands are separate profiles. All fixture
files, including backend/E2E sources and lockfiles, are restored by hash.

The first strict HTTP pair was 13.599 / 26.581 s. That slower candidate sample
has no accompanying profile/counters and remains unexplained. Four follow-up
strict checks use new response-header values: the ordinary pair is
11.464 / 11.412 s; the separate reverse-order profile pair is 11.545 / 10.723 s.
Both profiles show exactly one required Go build (7.964 / 7.953 s) and one test
process. On the candidate, the build is now underneath **service startup**,
rather than eager `withFile` construction. The outlier was not reproduced; that
does not retroactively identify its cause.

The committed portable regression runs on ordinary hosts. Both new and restored
sources remain pending through metadata/Service construction, then surface the
original error on filesystem demand. The unchanged production baseline fails
at construction. Schema and interface unit/race suites pass on the applied
sources. Separate privileged tests also verify successful bytes, mode, numeric
and inherited ownership, unchanged parent state, and actual byte consumption
after capture/reopen. The initial portable test omitted its required rootfs
resolver; that rejected fixture attempt is recorded separately and corrected.

## Independent allocation improvement

Interface reconciliation now materializes each consulted interface's visible
field signature once per locked reconciliation pass/view. If there are `P` pair
checks, `I` consulted interfaces and `F` fields, signature construction changes
from `O(P·F)` to `O(I·F)`. Pair enumeration and greatest-fixed-point elimination
remain unchanged. Permanent-only relationships avoid the memoizer entirely.

The focused 100-object benchmark improves 2.033 → 1.289 ms and 2,033,578 →
514,211 bytes per operation. In the broader 279-command matrix, expanded-listing
allocation falls approximately 701 → 671 MB with this change, but wall time is
1.535 → 1.504 s. Adding the experimental Dang scalar/nil clone optimization
reduces allocation further to 666 MB while wall time is 1.532 s. These results
do not establish a broad command-speed gain. Only the independent DagQL change
is included in the normal engine; Dang clone work remains an experimental
dependency patch.

The [complete matrix](collections-allocation-matrix.md) retains all nine UX
flows, first-volume diagnostics, disk/CPU counters and the limitations of older
recurring-edit measurements. The [evidence archive](collections-qa-performance-data/lazy-source/)
contains numeric samples, source/build hashes, drivers, profile aggregates and
test provenance. Raw profiles, Cloud output and credentials remain private.

## Relationship to ongoing work

The public PR review on 2026-09-26 found no duplicate source-pending copy fix.
This completes another boundary after the merged
[file/service laziness fix #14288](https://github.com/dagger/dagger/pull/14288),
using the existing framework from
[lazy part acquisition #14229](https://github.com/dagger/dagger/pull/14229).
[Remote-cache verification #14241](https://github.com/dagger/dagger/pull/14241)
remains relevant to persisted dependency behavior; distributed caching does not
repair the local decision to demand a producer unnecessarily.

[Yves's Go SDK work](https://github.com/dagger/go-sdk/pull/35) targets a separate
code-generation/runtime cost. It should be reused for cold startup work.
The analogous `Container.withDirectory` boundary and local telemetry
serialization remain separate candidates, not additional measured gains here.
