# Bounded module-load pipeline: no measured warm improvement

The isolated source/asModule scheduling prototype passed its targeted concurrency and correctness gates, but this matched local trial does not establish a user-facing latency improvement. Keep it experimental.

| Operation | Baseline median | Pipeline median | Samples per arm |
| --- | ---: | ---: | ---: |
| Warm `check -l --all` | 1381.70 ms | 1389.05 ms | 5 |
| Warm `list -a` | 1396.09 ms | 1407.42 ms | 3 |
| First-seen app comment → `check -l --all` | 1425.72 ms | 1436.11 ms | 3 |

All42 local commands produced their expected outcomes: exact14-row check listings, ordered artifact/workspace output parity, and actual native sentinel failure followed by successful restoration. The control and candidate used the same original CLI (`d6858098…`), Docker container driver, fixture paths, pinned SDK contents and retained engine volume. No Cloud calls ran. The original engine stayed stopped and its binary stayed untouched; fixtures and the owned temporary container were restored/removed successfully.

This uses four ABBA engine blocks, each primed with both exact listing commands after its restart. Samples are pooled observations from those blocks, not five independently randomized engine pairs. Each edit is a distinct first-seen `main.go` comment; it is a real source invalidation, not a claim that every lower content-addressed dependency is cold. The profile pairs run after all ordinary samples, each following an identical unprofiled listing primer without an intervening restart. Their instrumented wall times are excluded from these medians.

The candidate allows up to twice the existing outer job window while separately retaining the original bounds for source resolution and module registration. This can schedule a ninth source before the first eight registrations finish, and the regression test proves that scheduling behavior. It leaves legacy source policies, SDK resolution, indexed errors, cancellation joins and final publication unchanged. Source resolution can itself execute SDK work; these phases are not a clean network/CPU split. No fresh-volume cold, service-up, SDK code-generation or general throughput benefit was measured here.

All individual wall values, CLI/process-tree CPU, engine CPU and bounded I/O observations remain in `samples.json` and `summary.json`; the candidate warm-check outlier is retained. The existing fixture remains under a wide `/tmp`, equally for both arms. Metadata helper and Unix transport optimizations from separate experiments are not added into this comparison.

The separate wcprof pair verifies the intended scheduling change: the temporally ninth top-level source begins at185.73ms in the control and38.74ms in the candidate. The catalog interval changes from655.53 to631.74ms, collection expansion from869.92 to867.62ms, and the union of query intervals from1556.39 to1530.80ms. Both profiles contain seven Git advertisement requests and six runtime processes, with zero dropped events or unfinished operations. This is an earlier dispatch witness, not a147ms command saving: the earlier work substantially overlaps other work. Inclusive phases must not be added together or subtracted from ordinary CLI medians. One profiled pair does not establish a stable catalog benefit.
