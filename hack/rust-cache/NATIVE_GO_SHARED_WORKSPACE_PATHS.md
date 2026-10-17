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

Investigation moved to the [quadratic restored-posting removal path](NATIVE_RESTORED_POSTING_REMOVAL.md). The after-module wcprof driver is prepared but has not run, so an API-count reduction remains unverified. No PR is prepared for this inconclusive module experiment.

[Fork branch](https://github.com/grouville/go/tree/experiment/shared-workspace-paths) and [archived sources and observations](experiments/go-shared-workspace-paths/).
