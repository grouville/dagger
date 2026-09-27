# Prune unrelated static artifact trees before rebuilding schemas

One production-file overlay, two new focused test groups and an offline reduction of an existing profile. Focused normal and race gates passed (19 test/subtest entries in each, including three existing metadata checks). No engine build, runtime, Cloud or network call has run for this candidate. Production sources are unchanged.

The new candidate removes metadata work from exact artifact lookups. It does not cache an evaluated receiver, suppress a function call, resolve a default early, or extend any DagQL cache lifetime.

`Address.container` calls `resolveWorkspaceArtifact`, which calls `collectArtifacts` directly. `workspaceTargetModules` narrows new module loads, but a live workspace's `workspacePrimaryModules` returns all modules already served to that client. `collectArtifacts` then rebuilds each module's artifact tree and every configured SDK's engine-managed generator tree before filtering individual paths. Therefore an exact target such as `backend/go-test-base` can traverse unrelated metadata which cannot appear in the answer. The number of already-served modules is a source-level opportunity; it is not proven to be all nine modules in the recorded Address context.

The patch inserts a conservative module-prefix filter after the existing loading/config/entrypoint work. It applies before both `ModuleArtifactNodes` and `NewArtifactTree` for SDKs. Only known literal module prefixes are optimized. Wildcards, braces, escapes, malformed patterns and unknown prefixes retain the old full traversal. Every entrypoint remains eligible because a promoted path may collide with another module's prefix. SDK inventory/config construction still runs, so unrelated configuration validation has not been suppressed. The normal per-node matcher, ordering, ambiguity check and module-load failure handling remain in place.

This reduces tree construction from all returned modules/SDKs to the selected modules plus entrypoints. It still scans the small configuration/name lists. There is no cross-request data structure. The ordinary unfiltered catalog is unchanged; the expected benefit is its repeated narrow lookups during expansion and selected commands.

## Measured location, not a speedup forecast

The retained baseline split-init diagnostic is a fully primed listing on the ordinary heavy-init engine, separate from ordinary timings. Its `Artifacts.__itemsJSON` interval is 786.44 ms, with zero open/dropped operations:

| Phase | Observation |
| --- | --- |
| First configured Address.container | 363.43 ms |
| Actual backend constructor within it | 99.47 ms |
| Actual backend goTestBase within it | 123.96 ms |
| Go.modules after the first base | 285.01 ms |
| Three repeated base resolutions | 33.97 / 33.21 / 30.21 ms, overlapping |
| Parallel test discovery | maximum 90.94 ms |

Each of the three repeated Address calls contains 195 `Query.typeDef` calls and 273 `TypeDef.withOptional` calls even though both backend authored calls are cache hits taking only ~0.01 ms each. The earlier Unix profile shows the same structure with a 551.05 ms expansion and about 31 ms of overlapping repeated Address work. These observations locate removable metadata processing; they do not show how much this patch saves.

The first Address also contains a 64.80 ms single `Query.typeDef` observation in this profile. Its cause is not established; it must not be described as 64.80 ms of computation or subtracted as a guaranteed benefit. Nested inclusive totals overlap. The two authored calls, most Go.modules work and test discovery remain necessary under this patch.

## Why the held receiver-prefix cache remains unsafe

Suppose a `NEVER` constructor increments a counter and its collection includes that counter in each item's source. Enumerating the outer collection and selecting a nested item's collection are separate existing constructor occurrences. Reusing the first evaluated root for the second occurrence changes the item source and skips the second side effect. Equal syntactic selectors do not establish equal call occurrences: `PER_CALL` adds identity and a fresh result deliberately.

Even an ordinary cacheable constructor may have dynamic inputs which read the current workspace. A method between collection levels can export a source edit and advance the workspace read epoch. Reusing the old parent bypasses that observation. A request-local map keyed only by a path/module is therefore insufficient. The current patch avoids this problem entirely: every existing `Artifact.Evaluate`, `DynamicInputsForCall`, constructor and actual selected method still executes through its original path.

## Correctness gates passed

The tests exercise a narrower-work witness for exact backend/collection/SDK targets and use the existing complete `matchWorkspaceInclude` implementation as an independent oracle. They cover kebab/camel spellings, multiple modules, unqualified entrypoint selection, promoted-name collisions, transparent nested collection nodes, wildcard/union/invalid pattern fallback, and immutable input slices. A pruned tree must contain no matching node and no ordinary matcher error.

These are metadata selector tests, not a substitute for a full engine correctness run. Before adoption, validate the actual listing's ordered14 rows, selected real check and entrypoint/SDK generator paths against the original stack, plus a profile showing that the repeated metadata work falls. A malformed unrelated module which can be served but whose artifact-tree construction fails is an error-surface edge to examine: loading and recorded load failures remain unchanged, but an intentionally skipped unrelated tree will no longer undergo that late construction. No broad no-regression or wall-time claim is made yet.

The prepared files are `source/core/schema/artifacts.go`, `source/core/schema/artifact_static_prune_test.go`, `source-overlay.json`, `test-overlay.json`, and `prototype.patch`. Exact source/profile hashes and fixed-label numeric observations are retained beside this report.

The normal gate took 47.90 s and the race gate 83.77 s including compilation; these are validation setup durations, not product latency. Exact commands and test outcomes are in `validation.json`. No microbenchmark of only the prefix predicate is used to estimate the benefit: a meaningful follow-up must count actual tree/schema work and time ordinary commands.
