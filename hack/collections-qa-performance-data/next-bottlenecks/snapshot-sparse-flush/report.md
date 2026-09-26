# Snapshot Flush: avoid enumerating untouched image entries

Status: source review and isolated regression/benchmark source prepared.
**No production patch, builds, tests or measurements have run here.** The CLI
DiskWriter candidate remains owned by the cold-IO agent and is unchanged.

`internal/buildkit/snapshot/diffapply_linux.go:436` restores directory mtimes
with a full WalkDir of the destination, although `dirModTimes` already names
all directories requiring restoration. This makes Flush depend on all entries
in the snapshot's writable destination/upperdir. The same known-directory
visitor proposed for DiskWriter can remove that enumeration.

## Shared API and caller semantics

Coordinate the extraction with the cold-IO agent:

```
fsutil.ForEachExistingDirectory(root string, paths []string, apply func(string) error) error
```

The helper copies/sorts known paths, validates containment, and memoizes Lstat
of relevant ancestors. It skips recorded paths whose ancestor was deleted or
replaced by a symlink/non-directory. It propagates errors for relevant paths,
keeps parent-before-child order, and never enumerates unrelated directory
entries. Its tests can inject Lstat to prove the number of metadata probes is
bounded by the distinct known ancestor paths. Memoize false descendants too,
so a removed ancestor does not cause repeated recursive CPU traversal.

Snapshot's callback must retain its current `unix.UtimesNanoAt` call with
`UTIME_OMIT` for atime, exact stored `unix.Timespec` mtime, and
`AT_SYMLINK_NOFOLLOW`. Do not convert Timespec to int64 nanoseconds merely to
reuse DiskWriter's timestamp representation. Enumerating all files is not
necessary to establish that a known path remains a reachable directory.

Complexity becomes O(K log K + A) metadata work, where K is the recorded
path count and A is the number of distinct ancestor paths inspected (plus
path-string costs), instead of reading N total destination entries. Zero
recorded paths can return immediately. The proposed slice API has a small
extra allocation/copy at each caller; measure small K as well as sparse
large destinations before selecting the final signature.

## Snapshot-specific correctness

- `applierFor` resolves the root symlink before storing it. `Apply` obtains
  destination paths through safeJoin/root-aware parent resolution. Recorded
  paths therefore refer to actual directory locations under the apply root.
- `applyCopy` records only directory mtimes. Multiple diffs can overwrite an
  earlier directory or delete its parent; stale entries intentionally remain
  in the map until Flush. Checking only the final leaf with no ancestor check
  would follow a replacement symlink and mutate another tree. The common
  helper must validate every relevant ancestor without following symlinks.
- Overlay mode points root at the physical upperdir, not the merged lower
  image. Whiteout character devices are non-directories and must be skipped,
  including stale recorded descendants. Opaque directories remain directories;
  restoring their mtime must leave the opaque xattr intact. No helper may
  resolve into a lower layer or follow whiteouts as directory entries.
- Hardlink bookkeeping and cross-snapshot inode exclusion are untouched. The
  helper handles directory timestamps only; linked files retain their inode
  relationships and times.
- No concurrent writer is expected between Apply and Flush. Caching a checked
  ancestor preserves that assumption; neither this helper nor the existing
  WalkDir offers a race-proof hostile-filesystem capability boundary.
- The visitor no longer reads unrelated directories or changes their access
  times. It does not reproduce incidental ReadDir permission failures for
  unrelated entries; that is intentional. Relevant stat/utime failures must
  remain visible.

## Critical scope limit

`diffApply` immediately calls `Usage()` after Flush. Usage still performs a
full WalkDir and stats entries to count unique inodes and subtract known
cross-snapshot hardlinks. That pass has a separate accounting purpose and is
**not removed by this change**. Therefore total diffApply remains dependent
on destination size. The proposed improvement removes one traversal, not all
snapshot work and not all cold/warm I/O.

If diagnostic coverage is missing, instrument the existing diffApply call
site around Flush and Usage separately using the existing wcprof convention.
One phase per operation is sufficient; per-path spans would distort the work.
Do not claim a whole-command gain from a Flush-only benchmark.

## Prepared tests and paired benchmark

`diffapply_flush_linux_test.go` uses the actual applier Apply/Flush methods:

- Source directory mtimes, including nanoseconds, survive descendant writes.
- Deletion, file replacement and an outside-target symlink skip stale child
  timestamps; the outside sentinel remains unchanged.
- Replacing a leaf with an opaque directory preserves the xattr and hardlinks.
- An actual overlay-style whiteout skips stale times when mknod is available;
  that specific test skips when the runner lacks the capability.

No real overlay mount is created; the tests exercise the physical upperdir
representation and applier rules directly. Existing overlay integration tests
remain necessary for broader mount/snapshot behavior before shipping.

`BenchmarkApplierFlushSparse` varies untouched image files (0/1,000/10,000)
and recorded directories (0/1/32). It exercises the actual Flush method and
excludes setup and Usage. Compile a baseline test binary and a candidate test
binary using the same new test file, with only the production Flush/helper
changed via a Go overlay. Then alternate repeated benchmark runs in a quiet
slot and compare allocations and medians. The candidate should be flat as
untouched file count rises, including no recorded paths; results must also
show small-destination overhead.

Suggested focused package selectors once root grants the build/test slot:

```
go test ./internal/buildkit/snapshot -run '^TestApplierFlush' -count=1
go test ./internal/buildkit/snapshot -run '^$' -bench '^BenchmarkApplierFlushSparse$' -benchmem -count=1
```

Use the established isolated build modfile/overlay environment where required.
No engine workload or Cloud export is needed for these local filesystem tests.
