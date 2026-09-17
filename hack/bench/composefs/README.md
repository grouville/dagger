# composefs + filesync inode CAS: materialization experiment

**No production engine behavior changes.** This branch adds an opt-in test to
the synchronous result-first CAS at `31064758056ac175f54941d6293eff1905df894a`.
It asks whether a composefs metadata image can replace full-tree hardlink
materialization. This is not a snapshotter implementation or an e2e speedup.

## Scope and invariants

- CAS arm: the existing `fileCacheCopy`, `layercopy.CopyToEmpty`, and synchronous
  publication. No new async machinery.
- composefs arm: the same verified CAS writer and key, with atomic no-replace
  admission. `mkcomposefs --from-file` references those backing files directly.
  No intermediate hardlink tree, different blob store, or rehashed fs-verity CAS.
- Unmodified upstream composefs v1.0.8, commit
  `858ce1b38e1534c2602eb431124b5dca706bc746`. The native mount uses EROFS and
  overlayfs; no filesystem code is copied into Dagger.
- Metadata encoding, image construction, mount startup, and two full content /
  semantic-metadata verification passes and unmount are measured separately.
  wcprof records the diagnostic run; the second cohort disables instrumentation.
  CAS admission is included, not deferred past request completion.
- Every result must match bytes, type, permissions, ownership, mtime, symlink
  targets, path set and hardlink relationships. Independent equal-content files
  must not become aliases. Directory sizes and physical link counts are not
  portable semantic comparisons. The destination root is a wrapper, not an
  imported inode (`CopyDirContents`); only its directory type is compared.
- Stores and source copies are experiment-owned. Payloads remain alive until
  unmount; mounting occurs in a short-lived private container namespace.

## What the numbers do not mean

The input manifest is captured by a common full scan/hash before each arm. This
is not the Dagger client scan, and is outside materialization timing. It warms
source page cache. “Cold” therefore means **empty CAS**, not cold disk, engine
installation, toolchain delivery or cold CLI. No global page caches are dropped.

The test forces materialization even for an unchanged tree. Real filesync checks
for a retained complete result first and normally skips this work altogether.
These rows must not be presented as ordinary unchanged-command latency.

`first_read_verify` includes traversal, reading every byte, hashing and metadata
assertions, not just I/O. Report `ready + first_read_verify`, unmount and the
two-read total to detect work moved to the consumer or teardown. The one-read
sum adds unmount measured after the second pass, not a separate one-read trial.
A Rust compiler accesses a different subset; this is not a
Cargo benchmark. Native mounts and plain host directories also do not reproduce
every cost of Dagger's overlay-backed mirror and snapshot lifecycle.

The diagnostic CAS arm enables the existing per-operation copy collector. Set
`COMPOSEFS_BENCH_PROFILE=0` to disable wcprof and the copy collector on both arms
for an uninstrumented confirmation before promoting a timing win.

No writable-descendant, persistence/restart, portable platform, or GC integration
claim is made. A real snapshotter must retain both metadata and payload owner
across descendants and restarts. Mounting only a Directory handle is insufficient.

## Reproduce

Build the upstream C tools using their Meson build, then compile the opt-in test:

```sh
CGO_ENABLED=0 go test -p 2 -tags composefsbench -c -o /tmp/filesync.test ./engine/filesync
```

Run the test in an isolated Linux mount namespace with EROFS, overlayfs and
mount permissions. Set these environment variables to absolute paths visible
inside that namespace:

```text
COMPOSEFS_BENCH_SOURCE    private, stable fixture copy (no .git or target)
COMPOSEFS_BENCH_ARM       cas | composefs
COMPOSEFS_BENCH_CACHE     private persistent CAS directory for this arm
COMPOSEFS_BENCH_OUT       new sample directory, parent already exists
COMPOSEFS_BENCH_CASE      descriptive label
COMPOSEFS_BENCH_MK        upstream mkcomposefs executable
COMPOSEFS_BENCH_MOUNT     upstream mount.composefs executable
```

Execute `filesync.test -test.v -test.run '^TestComposefsMaterialize$'`.
Accept a sample only if the process exits successfully, including unmount.
Output: `result.json`, `wcprof.json`, and composefs image/dump where applicable.
Use separate stores for paired arms; keep one store through cold, edit, mixed
and reorganization flows, and alternate arm order between rounds. Preserve every
failure and outlier. Record fixture and tool pins alongside results.

## FUSE smoke-test finding

The unmodified C FUSE tool mounted the tiny image but failed to open a backing
file named `payload`: its `cfs_open` passes a length-delimited redirect xattr to
`openat` as a NUL-terminated string. The dump displayed trailing `\\xff` padding.
Current upstream `ec2573a0` still has the same open path. No workaround was added;
native mounting of the same image passed. FUSE is not a measured arm here.
