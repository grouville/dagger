# Three discovery setup experiments

Three further Go-module experiments do not establish a useful complete-command speedup. Keep them unselected. The existing snapshot-directory change remains the selected module baseline; the lower baseline times in these new cohorts are not additional demonstrated gains.

Each comparison uses four balanced pairs per workload on real dagger/dagger, with a fresh CLI and real source edits on a warm engine. Telemetry, ordinary GC, successful cleanup and final log flushing remain included. Both versions finish the test-addition/removal initialization before measured pairs. All **72 timing commands** return the correct ordered names and full rows and exit successfully; initialization has 4,399 rows, later commands 4,398. No profiler, build or check runs alongside timings. These experiments do not measure cold-start improvements.

| Experiment | Test-file edit | Faster pairs | Ordinary-source edit | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Retain compact ownership facts instead of configured module objects | 10.59 → 10.53 s | 2/4 | 6.40 → 5.92 s | 2/4 |
| Search source markers across discovered module trees in one call | 10.96 → 10.97 s | 2/4 | 6.16 → 6.01 s | 3/4 |
| Overlap independent test-file searches with list selection | 10.33 → 10.69 s | 1/4 | 6.05 → 5.88 s | 3/4 |

Compact owners reduce test-edit allocation **15.39 → 13.28 GB** and getter parent JSON **81.4 → 55.0 MB**. However, median paired latency is 0.12 seconds worse. Its profiles retain 804 evaluations and 1,494 SDK requests. This is a resource saving, not proof that it makes listing faster. The new check verifies custom base images and Go flags, nested owners and test exclusions on both versions.

Cross-module marker batching removes work: separate lossless captures record **81 executed workspace searches → 2**, and SDK requests **1,494 → 1,257**. Test-edit latency and allocation remain flat, with higher median CPU. About 105 changed production lines and additional scope/classification state are not justified by this result. The fixture covers overlapping/disjoint module trees, an unowned file, a module path containing a space, cwd changes, overlapping directives, edits and selections.

Parallel file search preserves sorted file order and output, but test-edit CPU rises **52.30 → 57.11 CPU-seconds**, and allocation **15.41 → 15.48 GB**. Ordinary-source edits reuse discovery and do not exercise this function; their small median difference is not evidence for this change. Existing checks and an expanded file-order fixture pass. This variant first exposed a [separate nested-selection type bug](NATIVE_DANG_NESTED_SELECTION_ELEMENTS.md); the corrected interpreter is common to both timing arms.

Its lossless captures retain 804 evaluations and 1,494 requests. The single profiled candidate completes faster (10.06 versus 10.60 seconds), despite the unprofiled regression. Captures diagnose work; they do not replace the balanced latency comparison.

Eight focused commands pass for compact owners, eight for marker batching, and seven for parallel search. The initial bracketed-module-path fixture fails on both marker versions; replacing that path with a space passes on both. The initial sources and failures are preserved as a separate unresolved discovery bug, not attributed to batching or silently discarded.

## Sources and conditions

All candidates have parent `grouville/go` commit `a3d0e4bf562b834c31135bff24e5931fd32b3acc`. Local commits are `5238186be7fc0fc39cc746d28bdb226e5c990b13` (owners), `77f0a49389ef3a5a1ad85d50272f291f5433e062` (markers), and `4dd99956b7fd223295b96a211902796311ca0785` (parallel search). None is selected or opened as a PR; complete sources and patches are archived.

The first two use engine SHA-256 `37d4c555e4c5bf4370f7aa70b653a53b576ba08fa9c615898bb03bff6b8eb122`. The third uses `053e9d5db9959b04259d48b8fc635721cfc7375652b43953010f767f7bf16118`, which adds only the independently tested nested-element type fix to that overlay. Both arms of every comparison use the same engine and CLI (`97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`). Shared function metadata and experimental sorting remain disabled. Source, configuration and temporary diagnostic switches are restored.

The Go engine restarts gracefully with its existing volume; the original Rust engine stays unchanged. Shutdown takes 137 seconds, with captured stacks in cache-state persistence, including imported content hashes. This shutdown cost is outside listing timings and remains a separate investigation.

[All evidence](experiments/go-discovery-setup-screens/), [selected improvements](GO_COLLECTION_IMPROVEMENTS.md), [next structural target](GO_COLLECTION_THREE_SECOND_PLAN.md). Fewer operations, lower allocation and faster isolated phases must still earn their place with complete-command measurements.
