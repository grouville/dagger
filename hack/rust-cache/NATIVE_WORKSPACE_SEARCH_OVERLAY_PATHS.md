# Search explicit paths created by host workspace overlays

Current main fails `currentWorkspace.withNewFile(...).search(paths: [...])` when an explicit path exists only in the overlay. Host ripgrep receives the missing physical path and fails before the engine merges overlay results. A new parent directory fails the same way; mixing an existing host file with the new file also fails.

The Go batching experiment exposes this through the real collection check. A separate direct GraphQL query reproduces it without loading the Go module. `git ls-remote` verifies upstream main is `ff0b029a4d`; the relevant search functions and overlay predicates match the controlled engine exactly. Unrelated parts of the source files differ, which is recorded rather than treating the whole files as identical.

The fix excludes overlay-owned operands from host search. If an operand is an ancestor of an overlay edit, it checks the base source before including that path. Overlay results are merged even when no host operands remain. Untouched missing paths retain the original error. Existing mount filtering and immutable directory searches keep their source selection.

The standalone branch changes three files: the resolver, a focused source-path regression and one real CLI integration test. The implementation introduces no shared state or locks. Its extra existence check runs only for ancestors of overlay edits or mounts. The per-search overlay checks follow the existing touched-path scan; no new persistent index or storage format is involved.

| Integration case | Main engine | Fixed engine |
| --- | --- | --- |
| Explicit overlay-only file | Missing-host-path error | Correct match |
| Mixed host and overlay files | Missing-host-path error | Both matches |
| Newly created parent directory | Missing-host-path error | Correct match |
| Unrelated missing path | Original error | Original error |

The unit regression fails on unmodified current main. The fixed source-path, mount-filtering, merge and scope tests pass under the race detector. The integration test independently reproduces all three failures before replacement and passes every case afterward. Go collection and retained-package checks then pass, including overlays, Unicode, stable ordering and selected execution.

The fixed search functions are transplanted into the retained development engine without replacing unrelated code. Native-cache checks pass before replacement, on their first calls afterward and after the complete Go cohort: **130/130, 1,026/1,026 and 6/6**, twice each. The engine exits gracefully in 180.10 seconds, retains the same volume, and runs `00166f29` afterward. This setup is separate from measured command cleanup. Profiling is off at the end.

This is a correctness fix that enables a performance experiment. A listing-speed improvement attributable to this engine fix is unmeasured. The Go-module comparison uses it in both arms.

[Code on the fork](https://github.com/grouville/dagger/tree/fix/workspace-search-host-overlays), commit `744ec940`, is based directly on main `ff0b029a`. Its [review description](upstream-prs/workspace-search-overlay-paths.md) is ready. This is the seventeenth prepared Dagger proposal, separate from the one prepared Go-module proposal. No PR is open.

[Reproduction, exact source, before/after regressions and retained-cache evidence](experiments/workspace-search-overlay-paths/).
