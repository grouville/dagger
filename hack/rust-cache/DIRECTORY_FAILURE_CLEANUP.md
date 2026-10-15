# Release failed directory exclusion snapshots

The 1,026-crate root-package experiment failed while mounting a long chain of
directory exclusions. Inspecting that failure exposed a separate lifecycle bug
on upstream main: `Directory.withoutPathsFromSnapshot` creates a mutable ref,
but returns mount and commit errors without releasing it. Ending the operation
lease does not release that Go ref. It remains locked in the snapshot manager.

The standalone [fix and regression](https://github.com/grouville/dagger/commit/e56011c66)
are based on upstream main `5d313bf2e`. No upstream PR has been opened.

The regression uses the real local snapshot manager and injects a mount failure
after it creates the mutable snapshot. It ends the operation lease, then checks
that the unreturned ref has been removed and the parent file is intact. The
second case cancels the operation during the failure, requiring cleanup to use
an uncanceled context. Both cases fail on main with `is locked: locked` and
pass under race detection with the patch. The existing shared-mount lifecycle
test also passes.

The fix releases the ref only when the operation returns an error. Successful
commits already consume it, so success does not acquire a new manager or ref
lock for cleanup. On failure, the mount helper has closed its mount before the
deferred release runs. Release uses the manager's existing lock order, and a
cleanup error is joined with the original operation error. No ref is published
by this failing path.

This releases the unreturned mutable reference after errors. Filesystem usage
and steady-state command speedups have not been measured. Batching package exclusions is the measured
performance improvement; this is an independently reviewable engine fix found
while investigating its failure case.

Focused check:

```sh
go test -buildvcs=false -race -count=1 ./core \
  -run '^(TestDirectoryWithoutReleasesFailedMutableSnapshot|TestMountRefSharesSnapshotMounts)$'
```
