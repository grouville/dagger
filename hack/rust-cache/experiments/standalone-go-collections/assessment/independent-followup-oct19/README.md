# Independent Go collection follow-up, 2026-10-19

Two recovered proposals now have drafts: [avoid rescanning span children](https://github.com/dagger/dagger/pull/14738) and [search only a package’s test files](https://github.com/dagger/go/pull/68). Both use standalone source changes, rather than the earlier combined experimental stack. The manifest records exact heads and bases.

## Complete listing measurements

Go module main is `334136faaa`; both arms use the same upstream engine `80699ac67a`, with its unchanged Dang dependency. Each measured command starts a fresh CLI, edits an ordinary Go source comment and a test-file comment, and lists all test rows. The engine is warm. Telemetry exports to a local receiver; ordinary cache and GC policies stay enabled. Profiling is disabled during timing. Setup adds a real test, then removes it, and checks both outputs before measured edits.

The fixed-configuration cohorts give each arm its own Git root and configuration. Only the module source differs. All expected names, row order and successful process exits are checked. Allocations are cumulative engine allocation during the command, not peak memory. Sampled cgroup memory is retained as a diagnostic and does not establish a standalone memory improvement.

| Package-local file search | Main median | Change median | Faster pairs | Allocated bytes, main → change |
| --- | ---: | ---: | ---: | ---: |
| 16 packages, 128 tests | 18.91 s | 11.16 s | 4/4 | 7.06 → 3.89 GB |
| 1 package, 8 tests, 1 file | 4.21 s | 4.20 s | 2/4 | 0.859 → 0.858 GB |
| 1 package, 128 tests, 16 files | 7.02 s | 8.10 s | 2/4 | 1.79 → 1.94 GB |

The many-file cost is real work: the change searches each file separately. Its paired median slowdown is 369 ms; the difference between separate medians is 1.08 seconds. These are different statistics, not interchangeable savings. A two-pair identical-code control measures 15.72 → 15.71 seconds, with one faster pair on each side. Individual runs vary substantially, and all observations are retained.

A separate wcprof comparison counts 2,176 → 256 matched-line reads, with no dropped events or open operations. The snapshots and individual calls are native Dagger operations. Timed runs do not enable this recorder. The existing collection execution check passes, including selected execution and expected failures. The new Unicode names preserve the existing matcher’s behavior. These fixture numbers do not establish a current-main full dagger/dagger listing time.

## Held proposals

The stricter parallel-discovery cohort measures 19.35 → 14.27 seconds on 16 modules, faster in 3/4 pairs. Engine CPU rises 42.65 → 52.78 CPU-seconds and allocations 6.09 → 6.73 GB. The baseline’s work depends noticeably on run order. The one-module control is 5.07 → 5.03 seconds, faster in 1/4 pairs, with more allocations. This deserves a more representative same-code control before publication; the earlier 14.85 → 7.32 second screen is not the confirmed headline.

Batching package selection measures 10.52 → 10.78 seconds on 16 main packages, faster in 2/4 pairs, with more CPU and allocations. Its behavioral checks pass, but no PR is justified by this cohort. The initial Go driver’s source contains a subsequently added batching task that the running interpreter did not load; batching was actually measured by the separate fixed-configuration script and samples here.

Shared generation matching is 12.60 → 12.47 seconds, faster in 2/4 pairs. Retained ownership is 26.34 → 24.97 seconds, faster in 3/4 pairs. The ownership and layout-change checks pass, but the benefit does not yet justify the added state and guards. Neither has a PR.

The two Dang changes pass current-main checks and improve their isolated construction/callback benchmarks. Their complete-command results remain variable and do not establish a reliable latency gain. They remain on hold. The typed-method negative check asserts an optimization invariant; it is not a user-visible correctness failure. The first malformed harness attempt and corrected check are both retained.

## Span indexing

The clientdb production file still matches live upstream main. The full clientdb race suite passes on baseline and the isolated patch. Fresh-index components improve 4,096 ordinary children from 25.64 → 2.05 ms, and cause-linked children from 26.36 → 2.16 ms, over six alternating pairs. Allocation counts are unchanged. One-child controls establish no benefit. The new small-command comparisons do not establish a complete-command gain.

The reason to propose the small span fix is the quadratic work recorded in a real full Go listing: more than two billion comparisons. The earlier complete listing comparison, 53.58 → 46.72 seconds across three successful pairs, used an experimental engine with other changes held constant. An additional baseline failed during cleanup and is excluded from successful latency statistics, but remains in the earlier report. Those figures are not stock-main results. The patch adds no map, lock or retained state; compatibility checks preserve repeated-ID and late-edge behavior.

[Earlier full listing report](../../../../NATIVE_GO_WIDE_TRACE_INDEX.md). Existing engines and volumes are retained. The four newly created matched runtime engines are retained too. A follow-up experiment is now checking whether one search over a package’s Dagger directory can remove the many-file cost while preserving files added through Dagger; it is not part of these published measurements.
