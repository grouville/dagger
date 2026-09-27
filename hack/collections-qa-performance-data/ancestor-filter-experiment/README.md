# Parent-directory synchronization prototype

Status: isolated normal/race tests and bounded microbenchmarks completed; see report.md. No engine/CLI benchmark or production source change.

`FileSyncer.syncParentDirs` (`engine/filesync/filesyncer.go`) synchronizes an imported host path's parent metadata before synchronizing the selected subtree. Its remote root is `/` (or a Windows drive root); it includes exactly the relative import path and excludes that path's children. `newLocalFS` applies the same filter to the mirror. The current filter prunes unrelated directories after receiving their entries, so it still enumerates and sorts all siblings at each level. This work repeats for independent imports even when their content is cached.

The candidate substitutes a direct ancestor-chain walker underneath the existing `fsutil.NewFilterFS`, for only that exact literal filter shape on a concrete host filesystem. It changes neither the protocol nor authority, actual subtree imports, ignore/mapping callbacks, freshness scopes, or cached snapshots. The general filter still controls parent emission and ordered stat mapping. Missing or non-directory intermediate components do not publish incomplete parent chains. Symbolic links are not followed by this walk; the import's earlier StatResolvePath RPC still performs the existing actual symlink resolution. `NewFS` retains its root resolution, and a root replaced after construction is checked again.

Per invocation, the direct traversal performs O(depth) filesystem operations, independently of unrelated siblings. Stats remain fresh and are read again when the filter emits included ancestors. No cross-call stat or lookup cache is introduced. This is a bound on touched entries/syscalls, not a claim that path-string work is strictly linear in depth.

## Conservative eligibility and known limitations

- Exact one clean, relative, literal include and matching `include/*` exclusion, no follow-path expansion, no wildcard/escape/negation ambiguity. Root filters and non-root Walk targets use the existing walker.
- Non-host/custom FS wrappers use the existing walker. Git-ignore wrapping remains outside the unchanged filter.
- Direct lookup on a case-insensitive filesystem can match a spelling that enumeration plus a literal filter would reject. This prototype therefore probes **every relevant ancestor on every walk** and only enables the path on Linux ext-family directories reporting no `FS_CASEFOLD_FL` through `FS_IOC_GETFLAGS`. Unknown filesystems, flags, access errors, non-Linux systems and changed/symlink parents fall back. The local benchmark roots report ext-family. No macOS/Windows performance benefit is claimed.
- The gate adds one open/fstatfs/ioctl/close sequence per ancestor, before the ordinary fresh walk. It is included in ordinary microbenchmarks. The deterministic operation-count test isolates the walk from this gate; both are bounded by depth.
- Directory opens reproduce normal read-access failure checks without enumeration. A filesystem fault surfaced only by reading directory entries (for example, an error in an unrelated directory block) may no longer be observed. This is an explicit semantic observation difference; the prototype is not asserted to be a universal transparent replacement for the full walker.
- Filesystem mutation races are not a new atomic-snapshot guarantee. Existing imports already have race windows. Tests cover relevant deletions, replacements, refreshed metadata and late parent stat collection; they do not prove every concurrent mutation interleaving equivalent.

Linux documents per-directory case-folding for ext4: [kernel ext4 documentation](https://cdn.kernel.org/doc/html/latest/admin-guide/ext4.html), retrieved 2026-09-26. This is why checking only the OS or root filesystem type would be insufficient.

## Tests completed

1. Same emitted stat objects and callback ordering as the existing full traversal for directories, files, symlink leaves, dangling links, missing branches and replaced intermediates. Mapping retains normalized metadata and GitIgnored flags.
2. Exact fallback scope for glob/escape/negation/normalization/follow/root filters and non-root traversal.
3. Fresh metadata across calls, original/root symlink behavior, root replacement, cancellation and map/consumer SkipDir semantics.
4. Deletion from the mapping callback before ancestor emission does not reuse cached metadata or emit incomplete ancestors.
5. Read-permission error behavior (injected for root-safe testing and actual permissions when non-root).
6. Actual `fsutil.Send` protocol: same ordered stat packets, file request IDs, data bytes, termination and bounded goroutine join. This is an in-memory protocol stream, not a full engine/gRPC integration test.
7. Deterministic work-count witness with 0/100/1000 unrelated siblings at four levels: old entry visits grow with width; candidate visits only the root and three ancestors. Microbenchmark includes the production filesystem gate.

## Upstream choices

The generic filter optimization is narrow and avoids wire changes, but case-folding probes add portability policy and syscall overhead, and directory-read error observations differ. An explicit internal **parent-metadata operation** could instead specify fresh literal path lookup rather than reinterpreting a user filter, under the same session-local filesync authority. That operation would need a versioned/compatible fallback for older clients, explicit root/symlink/error semantics, and the same ordered diff/copy tests. It would not permit reusing stale host snapshots. Measure the bounded prototype first, then decide which contract is justified; do not silently generalize it based only on Linux timings.

## Existing profile boundary

The saved CLI CPU profile attributes 170/100 ms to sender.walk and 80/60 ms to os.ReadDir across two listings. These stacks do not distinguish parent synchronization from actual subtree traversal. Ten Host.directory calls have about 154 ms summed inclusive duration, including three overlapping initial source imports. These observations motivate the experiment; they do **not** attribute all of that time to parent synchronization or predict a full-command saving.
