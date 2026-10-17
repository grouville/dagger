The combined CLI/engine profile found a nested `GomodGoMod.ownFiles` evaluation with 162 direct API requests, totaling 5.05 seconds of its 8.18-second query. Source inspection found one avoidable boundary: converting each module root into a workspace-relative path calls the public `gomod.workspaceRootPath` API, which reads the same immutable workspace cwd again. The trace does not prove that all 162 requests are those conversions.

The module experiment reads cwd once per operation and passes a private `WorkspacePaths` value through the local mapping callback. Its path conversion retains the original algorithm; the public helper remains a wrapper around the same implementation. This is a Go-module change written in Dang. It changes no engine behavior, cache identity rules or collection granularity.

Existing own-files, discovery, discovery-from-subdir, tests-collection and generation-globs checks pass. The source change is committed as `55260a3114c6556a5014e981bad7ed24fd39b842` on `experiment/shared-workspace-paths`.

The full-repository comparison is incomplete and the change remains unselected:

| Pair | Original module | Local path conversion |
| --- | ---: | ---: |
| Initialization, excluded | 52.16 s | 58.36 s |
| 1, candidate first | 43.66 s | 58.81 s |
| 2, original first | 60.15 s | 46.16 s |
| 3, candidate first | 74.29 s | 60.34 s |

All eight started commands return the correct rows and exit 0. The fourth pair never starts: idle admission reaches its 120-second limit during an ordinary metadata prune. The driver restores the source, module configuration, cache seeds and diagnostic modes. No attempt is discarded or replaced, and no aggregate improvement is claimed.

The engine log records a 158.19-second prune from 918,097 to 639,752 results, removing 79,517 persisted roots. It starts during the last 10.6 seconds of pair 3's original-module command, then blocks admission of the next command. Snapshot cleanup occupies the final 3.32 seconds. This accounts for that overlap and admission failure; it does not explain every earlier latency difference.

Investigation moved to the [quadratic restored-posting removal path](NATIVE_RESTORED_POSTING_REMOVAL.md). A subsequent profile confirms that the module change reduces direct API requests beneath the 80 `ownFiles` evaluations from 556 to 240. The largest evaluation drops from 162 requests to 3. Both profiled commands produce the correct 4,398 rows and exit 0, with no dropped or unfinished wcprof events. Profiled durations are diagnostic observations, not benchmark results.

A new, complete comparison enables the linear restored-posting deletion path in both arms. It retains ordinary GC, telemetry, the same engine and CLI, a fresh source edit and CLI process on every invocation, and the original collection granularity. The initialization pair adds a real test and is excluded; removing it in the measured pairs also checks discovery invalidation.

| Measured pair | Original module | Local path conversion |
| --- | ---: | ---: |
| 1, candidate first | 43.05 s | 46.16 s |
| 2, original first | 44.54 s | 46.82 s |
| 3, candidate first | 47.95 s | 45.95 s |
| 4, original first | 49.05 s | 41.97 s |
| Median | 46.24 s | 46.05 s |

All ten commands, including initialization, return the expected ordered rows and exit 0. The candidate wins two of four measured pairs. Engine CPU falls from a median 236.60 to 227.33 seconds and allocated bytes from 36.75 to 36.33 GB, but full-command time is effectively unchanged. The API reduction is real; a latency improvement is not established. The change remains unselected and has no PR.

The profile also identifies repeated schema preparation before successful SDK declaration-cache lookups. That engine work is the next experiment; reducing list comparisons or changing helper libraries is not supported by this profile.

[Fork branch](https://github.com/grouville/go/tree/experiment/shared-workspace-paths) and [archived sources and observations](experiments/go-shared-workspace-paths/).
