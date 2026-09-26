# Sparse local export: remove unrelated destination traversal

The real local-only `dagger -y generate render` fixture wrote the expected file, then failed after roughly 61 seconds while opening an unrelated directory under `/tmp`. Its generator itself was reported as 0.1 seconds. The CLI receiver's finalization path explains that behavior; these are not slow generator or Cloud-export measurements.

## Root cause

`core/changeset.go:1070` already exports only declared added/modified paths and their ancestors, with deletions sent separately. `engine/client/filesync.go:255` correctly forwards `Merge=true` to `fsutil.Receive`. `internal/fsutil/receive.go:174` uses an empty destination walker in merge mode, so the transfer's diff does not need the unrelated destination tree.

The unconditional scan happens afterward. `internal/fsutil/diskwriter.go:68` waits for file data and then uses `filepath.WalkDir(dw.dest)` to restore directory modification times. The directories needing finalization are already known in `dw.dirModTimes`. Even a file-only merge with an empty map walks every destination entry, and an inaccessible unrelated subtree can fail an otherwise completed export.

The isolated baseline reproducer proves the failure on a small, task-owned tree: it writes `generated.txt`, then `Wait` returns `open .../unrelated: permission denied`. The same test passes with the candidate. Neither test scans the actual `/tmp` tree or changes unrelated permissions.

## Candidate behavior and complexity

`DiskWriter.Wait` still waits for all asynchronous content writes. It then checks only the recorded directories and their ancestors with `Lstat`, rather than enumerating the tree. Relevant ancestor results are memoized only for this one finalization. Paths are sorted in the same parent-before-child order as the previous walk. Removed paths and subtrees replaced by files or symlinks are skipped; relevant filesystem and timestamp-setting errors still propagate. An empty directory set returns immediately.

The removed cost scales with all destination entries, even for one changed file. The new filesystem work scales with distinct ancestors of recorded directories; sorting scales with the recorded set. There is no persistent cache, time-based invalidation, new merge protocol, or dropped metadata operation. The existing platform-specific `chtimes` implementation remains in use. This is ordinary sparse application of a Dagger changeset.

Static replacement/symlink behavior is preserved. This patch does not claim race-proof containment against an adversary concurrently replacing path components; the old pathname-based traversal did not provide that guarantee either. A possible small follow-up is to memoize false descendant results when their ancestor is not a directory; current filesystem calls are already bounded.

## Validation

Seven focused tests pass, as do the existing filter tests and focused race tests. Coverage includes:

- No reads outside the recorded directory/ancestor set, using a counting/injection seam that remains effective under root privileges; an empty finalization performs no filesystem operation.
- Deleted directories, file replacement, parent symlink replacement, root symlinks, prefix collisions, relative roots, and relevant permission/timestamp errors.
- Deterministic parent-before-child ordering and one stat per shared ancestor.
- Asynchronous content completion followed by exact directory/file timestamps and executable permissions.
- Actual in-memory Send/Receive with merge preserving independent edits, non-merge deleting missing files, and symlink/hardlink correctness.
- The real write-then-unrelated-permission-error regression above.

No Dagger, registry, or Cloud calls were made for these tests. The original failing no-Git fixture remains untouched by this agent. The parent will validate the candidate on it and use a bounded project for comparisons, so the broken baseline does not traverse `/tmp` again.

## Local scaling measurements

Four runs in baseline/candidate/candidate/baseline order, with two samples per variant; 100 ms per benchmark case. Setup and verification are outside each timed loop. These are local filesystem microbenchmarks, not end-to-end CLI timings or durable-fsync claims.

| Operation | Unrelated files | Baseline | Candidate |
| --- | ---: | ---: | ---: |
| Write one tiny file and finalize | 0 | 0.0837 ms | 0.0714 ms |
| Write one tiny file and finalize | 1,000 | 0.740 ms | 0.0676 ms |
| Write one tiny file and finalize | 10,000 | 7.333 ms | 0.0697 ms |
| Write 16 tiny files and finalize | 0 | 1.083 ms | 1.086 ms |
| Write 16 tiny files and finalize | 10,000 | 8.587 ms | 1.066 ms |
| Finalize one recorded directory | 0 | 0.0246 ms | 0.00679 ms |
| Finalize one recorded directory | 10,000 | 7.485 ms | 0.00678 ms |
| Finalize 16 recorded directories | 10,000 | 7.559 ms | 0.0686 ms |

The candidate removes sensitivity to unrelated destination size in this experiment. It makes no material difference to 16 writes in an otherwise empty destination, where actual file writes dominate.

## Artifacts and attribution

- `diskwriter.go` and `diskwriter.patch`: isolated production candidate; no shared repository source modified.
- `diskwriter-baseline.go`: exact control source.
- `sparse_export_test.go`, `sparse_export_benchmark_test.go`: focused tests and benchmark.
- `build.py`, `build-provenance.json`, overlay JSON files, test/build logs: build and correctness provenance.
- `benchmark.py`, `benchmark-results.json`, `bench-*.txt`: raw scaling data and binary hashes.
- `dagger-disk-only`: candidate directory finalization with the original formatter source.
- `dagger-key-and-disk`: candidate directory finalization plus the parent's exact measured key-list formatter source.

Both CLI binaries use the same offline build flags as the previous CLI experiment, including `-buildvcs=false`. No engine binary change is needed to fix this client-side receiver path. The finalization benchmark was added after the CLI builds; `benchmark-results.json` records its updated source and dedicated benchmark-binary hashes, while `build-provenance.json` preserves the earlier build inputs.

The same full-tree timestamp-finalization pattern exists in `internal/buildkit/snapshot/diffapply_linux.go:441`. A shared known-directory visitor could serve both, leaving the snapshot callback's `UTIME_OMIT`/nanosecond semantics intact. That engine path is a separate experiment: its subsequent `Usage()` still legitimately walks the tree, so fixing `Flush` would remove one pass rather than make the entire apply operation sparse.

## Portable production revision

After the frozen measurements above, the relative-ancestor portability refinement passed the complete local fsutil unit suite and focused race tests. It also memoizes false descendant results. The Windows-only path test is prepared but skipped on this Linux host. `production/dagger-production` was built separately, and the exact validated production sources were applied to the shared repository without a commit. No new whole-CLI timing is attributed to this binary yet; the parent owns that comparison. See `production-review.md`, `production/validation.json`, and `production/applied-source.json`.
