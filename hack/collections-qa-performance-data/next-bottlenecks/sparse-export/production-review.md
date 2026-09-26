# Production preparation: DiskWriter only

The proposed patch is `production/sparse-export.patch`. It changes exactly:

1. `internal/fsutil/diskwriter.go`: replace the unconditional final tree walk with the private known-directory finalizer.
2. `internal/fsutil/diskwriter_test.go`: seven semantic/regression tests plus a Windows-only path-spelling/volume test.
3. `internal/fsutil/diskwriter_benchmark_test.go`: actual write-plus-finalization and recorded-directory finalization benchmarks against unrelated-tree size.

It introduces no public helper/API and does not change the snapshot applier. The measured version remains frozen in `diskwriter.go` and the two previously built CLI binaries. The production revision uses the portable refinement. It passed the complete local `internal/fsutil` unit suite and focused race tests, was built as `production/dagger-production`, and its exact tested sources were applied to the shared repository without a commit. `production/validation.json` and `production/applied-source.json` record hashes and commands.

## Read-only portability and lifecycle review

- `HandleChange` records keys produced by `filepath.Join(dw.dest, p)`. The wire receiver validates clean relative paths and parent-before-child order before handling them, so ordinary keys preserve the destination spelling.
- The portable finalizer nevertheless recurses using relative components, stopping at `.` rather than comparing absolute path spelling. This avoids nontermination when Windows `filepath.Rel` accepts different case for the same drive/root. Different volumes and paths outside the root fail before any filesystem access.
- `filepath.Clean(dest)` handles trailing separators; relative destination roots remain supported. The original key remains the timestamp lookup and callback argument, while stat checks anchor relative components to the selected root.
- Recorded paths are sorted with the existing `ComparePath`, preserving the previous walk's parent-before-child order. Directory timestamps are applied only after all asynchronous file writes complete.
- A one-flush map caches both directory and non-directory outcomes. Missing or replaced ancestors stop traversal; relevant errors propagate. Empty timestamp maps perform no filesystem access. None of this state survives a transfer.
- No `Stat` call follows an existing symlink: checks use `Lstat`, and non-directories stop the branch. This preserves static parent/root-symlink behavior. The code continues to use pathname-based operations and does not claim concurrent adversarial replacement protection beyond the previous implementation.
- Only newly created directories enter `dirModTimes` today. The existing immediate metadata handling for already-existing directories is unchanged; this patch does not broaden which timestamps are finalized.
- The existing Linux/non-Linux `chtimes` implementations remain authoritative. The production test timestamp was aligned to 100 ns to be representable on Windows while retaining exact comparisons.

## Tests prepared

- `TestSparseDirectoryTimesOnlyVisitsRecordedAncestors`
- `TestSparseDirectoryTimesSkipsDeletedAndReplacedSubtrees`
- `TestSparseDirectoryTimesRootSymlinkAndRelevantErrors`
- `TestSparseDirectoryTimesPreservesWalkOrderAndSharedAncestors`
- `TestSparseDiskWriterWaitsForDataAndRestoresDirectoryTimes`
- `TestSparseReceiveMergePreservesUnchangedAndNonMergeDeletes`
- `TestSparseExportIndependentPermissions`
- `TestSparseDirectoryTimesWindowsRootSpelling` (requires Windows path semantics; no real Windows filesystem or link privilege needed)

The first seven passed on both the measured and production versions, including `-race`. The Windows-specific path test is present but skipped on this Linux host; its Windows execution is not claimed. Some existing semantic cases create real symlinks/hardlinks, so native Windows CI may need its usual symlink privileges. A Windows cross-compile alone would establish compilation, not execution of the path test.

## Remaining end-to-end validation

Focused unit/race validation and the separately named production CLI build are complete. Parent-owned end-to-end measurement of that production binary is the next step. Retain the original failing no-Git trace and successful measured-candidate proof as distinct evidence; do not silently relabel measured binaries as the portability revision. Use a bounded project for baseline comparisons. The baseline failure should not be rerun against the whole temporary directory.

`archive-allowlist.json` contains the exact small source, proof and result files; no CLI/test binaries or credentials are included. The list includes this review and the completed production validation records.
