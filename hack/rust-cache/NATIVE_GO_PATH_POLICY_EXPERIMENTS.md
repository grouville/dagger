The simple native regexp replacement for Go's ignored-path check is **unselected**. It preserves behavior but does not demonstrate a consistent complete-command gain in this cohort.

The original splits each relative path and calls a predicate for its segments. The candidate uses `containsMatch` with absolute string anchors and exact segment boundaries. This builtin and `Regexp.escape` already exist in the minimum supported engine's Dang v2.1.4 dependency; no library upgrade is needed.

| Pair | Before | Candidate | Outcome |
| --- | ---: | ---: | --- |
| Initialization, excluded | 50.57 s | 61.97 s | New module source population |
| Measured 1, reverse order | 51.98 s | 52.31 s | Candidate slower |
| Measured 2, forward order | 55.28 s | 50.38 s | Candidate faster |

Medians are 53.63 → 51.34 seconds, but only one measured pair improves. Engine CPU is 251.27 → 249.26 CPU-seconds and allocation is 36.09 → 35.97 GB, both comparable. These observations do not establish that the native matcher is a better implementation for this workload. Keep the original policy.

All six commands return identical 4,398 rows and exit successfully. Both arms use the selected literal-path CLI, the same experimental engine and fresh source edits on a warm engine. Telemetry and normal GC stay enabled, with profiling disabled. The expanded public file-policy check passes against both implementations, including Unicode, newlines, case sensitivity, ignored segments and names that merely contain `testdata`. Invalid-fixture filtering, module discovery, Go test collections and generation-glob checks also pass. Initial formatter/VCS-stamping and test-grouping errors are retained separately from those passing checks.

The larger module-prefix experiment is also **unselected pending confirmation**. It retains the original ignored-segment policy and replaces per-file parent-path records with one cached prefix matcher per module. Escaped names, path boundaries, invalid fixtures, discovery, collections and generation checks pass against the original implementation.

Its measured pairs take 65.33 → 52.16 and 54.16 → 52.15 seconds. Every command succeeds with identical 4,398 rows. The first control has materially greater host contention: CPU pressure is 33.9% versus the candidate's 17.4%, and host IO pressure rises to 3.2%. Both second-pair arms have about 17–18% CPU pressure. Aggregate engine CPU is essentially identical, 251.68 → 251.38 CPU-seconds, and allocation is 35.91 → 35.81 GB. The nominal median 59.75 → 52.15 seconds must not be presented as a reliable module speedup. A clean confirmation would be needed before selecting it. The retained initialization pair takes 52.55 → 62.82 seconds as the new module source populates its cache.

These experiments do not change the selected Go module (`7568cd0`). The validated filesystem changes are retained independently.

The subsequent [engine profile with both selected filesystem fixes](experiments/go-post-filesync-profile/) completes in 53.89 seconds, exits successfully and returns the same 4,398 rows. This is a diagnostic capture with profiling, not another timing comparison. wcprof retains 559,748 events with none dropped and no open operations. Package discovery takes 21.03 seconds, expansion adds about 14.1 seconds and the final collection metadata projection adds about 8.0 seconds. The command still makes 963 SDK invocations.

Three five-second CPU windows contain 82.13 CPU-seconds. Background garbage collection accounts for 26.25% of sampled CPU; allocation accounts for 26.76%. These cumulative categories overlap and must not be added. The allocation profile attributes 2.32 GB to Dang's `NewType`, whose constructor eagerly creates nine maps. Creating those maps only when written is the next isolated experiment. The profile also records 3.13 GB in protobuf JSON marshaling and 0.80 GB in telemetry log flushes; neither telemetry coverage nor ordinary GC was disabled.

[Simple ignored-path matcher sources, all attempts and setup](experiments/go-native-path-filter/). No PR is proposed for this experiment.

[Nested-module prefix matcher sources, all attempts and setup](experiments/go-native-module-prefixes/).
