# Content-addressed filesync trees

Status: experimental implementation on `perf/filesync-cas`, based on
`82cc7d32d7a499a95c5b600d5bb6851d57613d96`. Enabled for Host.directory
imports on this branch; not a production-ready or measured performance fix.

## Problem

An edited Ruff import transfers less than 1 ms of changed file content, but
materializes a whole immutable tree. Three instrumented imports took
782–821 ms materializing, 62–68 ms committing, and 319–337 ms comparing the
source. `mkdir` accounted for only 16–18 ms of summed syscall durations;
creating files, copying bytes and restoring metadata cost much more.

Those are diagnostic raw-import measurements, not Rust module end-to-end
results. Syscall durations overlap and cannot be added as exclusive wall time.
The original captures are retained under
`/tmp/dagger-rust-devloop-focus.cCZvrPel/syscall-probe-r2`.

## Representation

Store file bytes and versioned directory nodes in the engine's existing
containerd content store. Each node describes its own metadata and sorted
children. A directory references child nodes by digest; a regular file
references its bytes separately from its metadata. Editing one file creates
its blob and new ancestor nodes, not a new copy of every file.

Names, link targets and xattr names are bytes, including non-UTF-8 names.
Symlinks are recorded, not followed by the store. Hardlinks refer to a regular
file within the complete tree; root validation must check that relationship.
Unsupported special files must fail explicitly or use the existing import
path, never disappear silently.

The storage digest includes materialization metadata. It does **not** replace
Dagger's existing content-equivalence digest, contextual-input validation,
session compatibility checks, or egraph identity.

The importer consumes the conflict-held, filtered change set without another
mirror walk. Engine-owned inode hints avoid re-reading unchanged payloads;
missing objects are re-ingested. Existing content-hash lookup can select an
older equivalent root, including its hardlink topology. That selected CAS
root, not just its old view, becomes authoritative. Missing optional hints
are misses; malformed metadata and storage errors remain errors.

## Ownership

Write blobs and nodes under an operation lease. Publish a result only after
all referenced objects are present and a result-owned lease has been attached.
Parent nodes carry containerd's standard `gc.ref.content` child links.

Existing snapshot-owner leases are flat: containerd does not follow child
links from them. Add separate non-flat content-root ownership, without
changing existing snapshot/image retention. Persist result-to-content links
alongside result-to-snapshot links, including undecoded results at startup.
Restore desired leases before deleting stale owners.

Shared-byte accounting must identify individual physical blobs, not charge
the full closure independently to each root. No immortal process map, fake
snapshot used as a lease anchor, or per-file DagQL result is needed.

## Materialization

Keep the public `Directory` API and ordinary standalone CLI commands. An
execution view is derived from its CAS root. A previous immutable view can
accelerate creation of the next one, but is not the durable source of truth:
reconstruction must succeed after discarding views and disconnecting the host.

Do not link mutable mirror inodes into immutable results. Do not mix writes
to an overlay upperdir with deletions through the merged mount: type changes
can leave whiteouts that the direct copier misinterprets. The materializer
needs real-overlay tests as well as portable filesystem tests.

The implementation uses an exclusively owned merged mount, confined os.Root
operations and existing snapshot/mount/xattr helpers. Parent reuse is enabled
only for overlayfs: native's parent copying changes directory timestamps, so
native reconstructs the tree instead. Complete-root indexing currently reads
all directory metadata; it is not a Merkle-pruned walk.

Directory checkpoints retain the root but not the derived snapshot. A real
DagQL/containerd test collects the view and reconstructs bytes and hardlinks
after manager/cache restart without any host or mirror. This is not yet a
full engine-process restart test.

## Review sequence

1. Deterministic tree format, validation and identity tests.
2. Streaming storage in containerd, child references and lease/GC tests.
3. Result ownership, checkpoint import/export and shared-byte accounting.
4. CAS-backed filesync import and derived snapshot materialization.
5. Correctness matrix and ordinary Rust check/generate performance evidence.

Each commit states what is wired in, its focused repro/tests, and whether
there is a measured user-visible change. Foundation commits are not
performance claims or production-ready fixes.

## Acceptance

- Preserve edits, deletions, renames, metadata, symlinks and hardlink groups.
- Retain old results under overlapping imports and concurrent callers.
- Handle cancellation, failed writes, ownership handoff, restart and pruning.
- Reconstruct without the host or a previous materialized snapshot.
- Test native and overlay snapshotters; preserve cross-platform host input.
- Retain all wcprof captures, failures and tails. Compare equivalent fresh
  edits, source validation and artifact export, not only exact cache hits.

The hypothesis is to remove much of the 782–821 ms full-tree materialization
cost. No CAS speedup has been measured. The remaining source scan and CLI,
module and Cargo costs still require separate work.

Current focused coverage includes independent legacy checksum parity,
filters/re-inclusion, missing blobs, hardlinks, overlapping imports, native
and overlay views, ownership/GC/restart, and public Host/File integration.
Before promotion: bound/compact long overlay chains; validate full engine
restart and cross-platform/remote-client flows; profile cold ingestion as
well as edits; run ordinary Rust check/generate comparisons. Per-blob content
commits and full metadata indexing can offset the saved copying cost.
