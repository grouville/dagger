# Explicit base Address: matched local Go module comparison

The opt-in module API reduced local expanded-check discovery from **1,392 to 1,138 ms** at the median and a first-seen application comment followed by the same command from **1,408 to 1,106 ms**. All 28 commands passed, including identical ordered fourteen-row checks and full artifact listings. This is a useful measured reduction, but discovery still exceeds the 500 ms objective.

The comparison used the same engine, CLI, ordinary init, SDK pins, workspace path and retained volume. Both Go modules were local sources with the same pinned remote gomod dependency. The control was original Go source with `base = "dag://backend/go-test-base"`; the candidate used the prepared module with `baseAddress` at the same location. The engine includes the small generic `UserDefault` Address correction and common opt-in tree profiling markers. It excludes the separately tested metadata pruning, helper extraction, split init, new Unix transport and held telemetry experiments.

## Ordinary measurements

Four correlated ABBA blocks ran a checks primer, two unchanged checks listings, two unique-comment checks listings, and one artifact listing. Two final primer/profile pairs are excluded below. All values are milliseconds, preserving every sample, including the first slower control observation.

| Operation | Control values | Candidate values | Median control → candidate | Aligned median difference |
| --- | --- | --- | --- | --- |
| `check -l --all`, unchanged | 1767.8, 1390.2, 1341.7, 1394.6 | 1124.4, 1151.9, 1242.6, 1114.0 | 1392.4 → 1138.1 (−18.3%) | −259.4 |
| Unique `main.go` comment → `check -l --all` | 1436.1, 1435.6, 1374.4, 1381.3 | 1161.4, 1064.2, 1099.9, 1112.2 | 1408.5 → 1106.1 (−21.5%) | −274.6 |
| `list -a`, after checks primer | 1368.1, 1348.5 | 1099.2, 1169.5 | 1358.3 → 1134.4 (−16.5%) | −223.9 |

All four aligned warm-check differences and all four aligned edit differences favor the candidate. There are only four observations per arm for these flows, two for artifacts; block alignment is not independent randomization. Artifact observations follow a checks primer and have no additional artifact-specific primer. Every comment used new bytes per call and arm. This invalidates the source snapshot but does not make every lower content-addressed result cold.

## What the separate profiles establish

Each profile immediately followed its exact listing primer. Both have zero dropped events and zero open operations.

| Boundary / work | Control | Candidate |
| --- | ---: | ---: |
| Expanded listing (`Artifacts.__itemsJSON`) | 599.6 ms | 374.4 ms |
| Catalog (`Workspace.artifacts`) | 498.6 ms | 570.5 ms |
| Address Container resolutions | 4 | 0 |
| Authored backend constructor executions | 1, 99.7 ms | 0 |
| Authored backend `goTestBase` executions | 1, 96.9 ms | 0 |
| Runtime processes | 6 | 4 |
| Module tree builds | 45 | 9 |
| Module tree inclusive sum / union | 72.94 / 52.40 ms | 10.38 / 10.38 ms |
| Core tree builds | 10 | 2 |
| Core tree inclusive sum | 0.915 ms | 0.149 ms |
| Git admission requests | 7 | 7 |
| Git admission interval union | 309.3 ms | 381.3 ms |
| Recorded operations | 20,084 | 17,173 |

The configured execution Container is no longer produced during discovery. This removes the two authored backend dispatches and repeated Address metadata traversal. The four remaining runtime processes happen before expansion and remain a separate opportunity; the comparison does not change their SDK path.

The new tree markers also bound the proposed core-tree factory idea: repeated core tree construction is below one millisecond here, so it is not a useful next implementation target. Module trees cost more, but the Address change avoids the extra whole traversals. Its savings overlap the separate scoped-metadata-pruning experiment and must not be added to that result.

Inclusive intervals overlap and must not be summed as command savings. Git counts are unchanged and its union is higher in the candidate profile; catalog timing is also higher. The single profile pair establishes work removal and its position, not a deterministic subtraction from every command. Runtime-process totals likewise include overlapping registration work and are not the critical-path saving.

## Semantics and correctness boundary

This is an explicit module API option, not an invisible lazy Container replacement. The existing `base: Container` path stays eager. With `baseAddress`, the Address retains its originating workspace and is consumed when execution needs the Container; producer/type errors move to that use. The user must replace the `base` setting with correctly cased `baseAddress`; supplying both is rejected. Both fields are optional, so neither contributes a new artifact row through `walkArtifactNodes`.

Before timing, the separate v5 correctness sequence passed nine CLI commands and ten retained-session RPCs. It checked direct NEVER producer behavior, actual base environment and real bound HTTP service, wrong-service failure, changed-test failure, recovery, exact listings and a real strict greetings HTTP test. Repeated consumption through a retained default-cached GoModule reused its outer base result, while direct NEVER Address consumption produced distinct generations. This is ordinary parent function caching, not a new guarantee that a nested NEVER producer runs through every parent cache hit. Earlier failed harness attempts remain preserved: they used legacy GraphQL typed IDs/loaders, corrected to current universal `ID` and `node` fragments before v5 passed.

The required producer work still happens when an actual check consumes the base. No actual-check execution speedup, service-start speedup, SDK-generation speedup, fresh-volume cold improvement or production Cloud benefit is claimed from these 28 calls. No cross-session authorization or cache shortcut was introduced for timing.

The temporary engine was removed, original engine/init remained unchanged and stopped, retained volume was preserved, and original/copy fixture bytes were restored. Measured command intervals recorded 28,798,976 bytes of engine writes; that bound excludes engine setup/shutdown and gaps. Raw outputs, profiles, tokens, runtime IDs and container details are excluded from the public evidence allowlist.
