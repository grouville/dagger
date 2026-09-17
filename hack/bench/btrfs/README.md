# Ruff: native Btrfs snapshots and manifest deltas

Research branch `exp/filesync-btrfs-delta`, based on composefs diagnostic
`4e7b0832`. **No production filesync/snapshotter behavior changes.** The opt-in
test implements the delta mechanism before adding engine ownership or platform
support. It uses standard `btrfs-progs`, existing Dagger copy/hash/metadata
helpers and the same semantic verifier as the earlier CAS experiment.

## Mechanism

1. Capture source and previous-result manifests outside the materialization
   timer, as the stand-in for already-synchronized metadata. This is a full
   scan/hash, not a fast host change detector.
2. Compare these manifests in memory, timed. Changed files, directories,
   deletions and affected hardlink groups become a delta.
3. Cold: create a subvolume and copy the source once. Warm: create a writable
   snapshot of the retained previous read-only result.
4. Apply only affected paths. Changed regular files use the existing verified
   writer. Preserve alias groups and restore affected ancestor metadata.
5. Mark the successor read-only. Include command startup and snapshot/seal
   transaction costs in `ready`.
6. Verify all bytes and semantic metadata twice. Verify the previous version
   again too. Retain both versions; do not flatten or delete older snapshots.

The delta arm does not add a separate blob CAS: Btrfs shares storage between
snapshots. It therefore does not supply the flat CAS's cross-tree content
deduplication. This experiment isolates structural sharing, not a complete CAS
replacement. Cold copy uses the same Dagger layer copier, without blob admission.

The current planner is O(N) over the supplied manifests. It does not reuse the
engine's radix hash tree yet. Directory renames are represented as delete/add;
the test is not handed a privileged list of rename operations.

## Compared arms and timing boundary

- `cas-ext4`: current synchronous result-first inode CAS on the host ext4.
- `cas-btrfs`: exactly the same algorithm on Btrfs, without native snapshots.
- `btrfs-delta`: native snapshots plus the verified manifest delta.

This is **not main versus a patched engine**, not host scan/transfer, not Cargo,
and not CLI latency. Input capture and full verification are separately timed.
`ready + first_read_verify` is also reported; a full-tree verifier is not an
actual compiler access pattern. There is no guarantee that cheap preparation
also means cheap first access.

All versions are retained in all arms. No per-result deletion cost is hidden in
an arm-specific background worker. End-of-experiment filesystem sync/unmount is
reported separately; crash recovery and production GC remain unvalidated.

Unchanged and repeated-tree states force materialization; a real complete-result
cache hit should bypass it. The last row revisits the edited tree after the
reorganization, so the delta arm applies the reverse changes rather than using
a historical-result lookup.

Cold means empty store and source data warmed by common capture, not an empty
host page cache or first installation.

## Isolation: do not share Btrfs transactions between arms

The first diagnostic put CAS-Btrfs and delta results on the same Btrfs mount.
That made snapshot creation susceptible to flushing the control arm's dirty
metadata. Keep that result as a confounded diagnostic, not a headline score.

Use independent file-backed Btrfs filesystems for the control and delta arms.
They still share the host physical device with ext4, so this is not a raw-device
production storage comparison. Four paired rounds reverse arm order. Existing
engines are not stopped, global caches are not dropped and kernel settings are
not changed. Record host activity and preserve every sample/outlier.

## Reproduce

Build the opt-in test from this worktree:

```sh
CGO_ENABLED=0 go test -p 2 -tags composefsbench -c -o /tmp/filesync.test ./engine/filesync
/tmp/filesync.test -test.run '^TestBtrfsDeltaPlanApply$' -test.v
```

In a private privileged container with `btrfs-progs` installed, provide:

- `/bench`: a writable experiment-only host directory, containing `filesync.test`.
- `/fixtures`: read-only frozen Ruff fixture copies from the earlier matrix
  (`original`, `edited`, `moved`, `mixed`, `reorg`).
- `/btrfs`: a private Btrfs mount for delta snapshots.
- `/btrfs-cas`: a **different** private Btrfs filesystem for the CAS control.

Never format an existing device. The recorded experiment formats only two new
regular image files under its own mktemp directory, then mounts them with loop
devices inside the container. Retain the images and unmount before stopping.

```sh
python3 hack/bench/btrfs/run.py --container CONTAINER --out /tmp/EXPERIMENT/profile --rounds 1 --profile
python3 hack/bench/btrfs/run.py --container CONTAINER --out /tmp/EXPERIMENT/matrix --rounds 4
python3 hack/bench/btrfs/sequence.py --container CONTAINER --out /tmp/EXPERIMENT/sequence --fixture /path/to/private/original --edits 128
```

`--out` must be a new directory directly under the host path mounted at `/bench`.
The sequence uses a private copy, half its edits repeatedly touch one file, and
half touch distinct source files. Every predecessor remains retained and checked.
This tests for growing per-edit costs, not sustained throughput under contention.

Use the maintained wcprof analyzer on the exported `*.wcprof.json` files.
Profiled and unprofiled cohorts stay separate.

## Engine integration, if the mechanism wins

Reuse containerd's existing Btrfs snapshotter rather than write one. This Dagger
revision exposes native/overlay/fuse-overlay and proxy snapshotters; adding
native Btrfs entails build/dependency and backing-storage decisions (containerd's
implementation is CGO-gated). The experiment's CLI wrappers are not a proposed
production backend.

The filesync change needs previous-result identity keyed by the complete import
scope, retained parent/hash state, conflict handling, correct fallback on GC and
restart, and normal result ownership. Snapshot layout must not change semantic
content hashes or leak mutable state into cached Directories. That wiring is
not implemented by this benchmark, nor is cross-platform provisioning.
