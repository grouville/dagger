# Skip unnecessary comparisons when ordering discovered paths

This is an independent Go-module change on main `8a1d6ad09c909a541e7e5fa319bddb5dba83d20b`, with the unmodified Dagger CLI and engine from main `23b004afe665eb4cc8a44767ba532fcb5cda2020`. It does not use the older experimental engine, Go module, compiler caches or host-glob CLI patch from earlier reports. The engine has its own retained volume, with no cache-policy overrides or forced collections. Binary hashes and build commands are in `builds.json` and `engine.json`.

Draft PR: https://github.com/dagger/go/pull/70. The clean fork branch is `grouville/go:perf/review-ordered-paths`, commit `461eadf61eba3cc9d7a4e3e24323c7835aa6b182`, with DCO. The two production files contain the same small change in three private helpers: if the new path belongs after the last accumulated path, append it; otherwise retain the existing insertion code. No public language API, cache, lock or additional retained state is introduced. The remaining insertion work and array copies can still be quadratic.

## Complete real-repository owned-file command

The command is `dagger api call gomod at --path=. own-files --glob=*.go`, run from the real Dagger repository at `c5456d9cbf47e432b89aba43e35211425e8e1f03` with its local `gomod` module installed. Each command returns exactly 2,511 paths, matched in order against an independent tracked-file inventory applying Go's ignored-path and nested-module boundaries.

| Metric | Main | Patch |
| --- | ---: | ---: |
| Elapsed time | 19.759 s | 3.152 s |
| Engine CPU | 49.267 CPU-s | 6.541 CPU-s |
| Cumulative engine allocations | 19.725 GB | 2.127 GB |

Four balanced pairs, faster in all four. One excluded initialization command for each variant precedes the measured pairs. Every invocation starts a fresh CLI and edits an ordinary Go source file. The engine, filesystem and module setup are warm. The module installation path and workspace configuration stay fixed; only the two production source files are switched between the main and patch versions. All ten commands validate the exact output and complete session cleanup. Telemetry and ordinary GC remain enabled; profiling is off during timings. Commands are strictly sequential.

The raw `source_and_config_fixed` flag means the input revision, module installation path and workspace configuration are fixed, not that source bytes are unchanged: `source_edit` and `module_hashes` record the intended edits. `owned-file-inventory.json` records the independent expected paths. Samples, command output and per-version source hashes are retained.

These are **complete owned-file discovery commands, not complete Go test-collection listings**. The peak-cgroup-memory samples are retained but do not establish reduced peak memory; allocation savings must not be described as RSS savings. No gain is added to another cohort's figures.

## Check the mechanism

Separate wcprof captures have zero dropped events and zero open operations. Both variants execute `GomodGoMod.ownFiles` exactly once and `Workspace.glob` exactly once; both return the identical expected list and complete cleanup. This rules out comparing one executed operation with one result-cache hit in these diagnostic runs. The profiles are excluded from the timing cohort.

The component benchmark reads the actual private helper source from each checkout and runs it through stock Dang v2.1.4, as pinned by the current main engine. Argument binding is shared. Input immutability and output sorting are checked before timing. Four balanced fresh-process pairs per case, three timed operations per process, GOMAXPROCS=8:

| 512 strings | Main | Patch |
| --- | ---: | ---: |
| Ascending | 674.487 ms | 6.537 ms |
| Reverse order | 10.618 ms | 14.635 ms |
| Shuffled | 341.748 ms | 352.965 ms |

The check adds cost for out-of-order input. Reverse order is about 38% slower and shuffled input about 3.3% slower in this component comparison. Eight-element controls are also retained; the shuffled case is 155.44 -> 182.28 microseconds. This is a targeted optimization for mostly ordered discovered paths, not a general-purpose sorting replacement.

## Correctness and limits

The same new public file-order check passes on main and the patch. It covers empty and singleton lists, Unicode byte order and `a.go` versus `a/b.go`, where directory traversal order need not be full-path byte order. The existing Go test-collection check passes on both versions, exercising nested modules, names, ordering and selected test execution. Its intentional failing nested test is caught and asserted by the parent check; both overall commands exit successfully. Dang v2 formatting passes. The final formatted public ordering check was rerun on both versions and passes; those logs are retained separately. `initial-before-format.patch` retains the pre-format test spelling; `go-sorted-inputs.patch` matches the published commit exactly. An initial mistyped check selector ran no checks and failed; its log is retained separately and is not counted as validation.

The remaining full test-listing command needs its own completed before/after comparison. A later full-output correctness smoke is separate from this cohort. It reached its 600-second limit without rows and therefore validates neither full output nor cleanup. A CPU/wcprof window was enabled during that smoke; it is not an unprofiled timing sample. No complete collection-listing speedup is claimed by the sorting PR.
