The next generic snapshot candidate is to restore timestamps from the set of
directories the operation already changed. Flush currently enumerates every
entry under the destination even though its map already identifies those
directories. A shared visitor can inspect only the known paths and their
ancestors, preserving deletion, symlink replacement and whiteout behavior.
This is source analysis with prepared tests, not a measured snapshot speedup.

The intended work bound is the number of recorded directories and distinct
ancestor paths, with sorting for deterministic order. It should avoid a sparse
edit becoming more expensive merely because an unrelated image directory has
thousands of files. Keep the existing timestamp representation, omitted atime,
no-follow behavior, opaque xattrs and hardlink ownership; do not add another
persistent cache or skip required source invalidation.

Measure Flush and Usage separately before deciding the end-to-end value.
Usage still scans the destination to account for unique inodes and
cross-snapshot hardlinks, so this candidate removes one traversal rather than
all snapshot I/O. A credible benchmark must show both small-directory overhead
and scaling with untouched files, then confirm an ordinary edit/check or
export improves. No milliseconds are attributed to this candidate yet.

If that accounting pass later dominates, investigate whether the existing
applier can maintain exact inode/block deltas while applying changes. Deletion,
replacement, duplicate hardlinks, lower-layer ownership and overwrite errors
make this a separate correctness problem. Reusing immutable snapshot accounting
may be possible, but should remain a hypothesis until validated against the
current full-walk result on adversarial multi-diff and hardlink fixtures.
