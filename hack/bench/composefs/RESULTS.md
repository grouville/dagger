# Ruff materialization: inode CAS versus native composefs

Date: 2026-09-17. **Research result, not a production engine change.**

Decision: retain the experiment; do not replace Dagger's snapshotter on this
evidence. Avoiding full-tree hardlink creation is a real improvement, but some
work moves to reads and unmount. Cold consumers regress. This is not an
across-the-board win or proof of faster Cargo / ordinary CLI commands.

## Setup

- CAS base: `31064758056ac175f54941d6293eff1905df894a`, synchronous result-first
  admission plus xattr skipping; no asynchronous-admission changes.
- Ruff: `c2cd236b9cc5b2149c74247e179d6567ec74066f`, copied fixtures only.
  12,025 imported entries plus the root; 89,442,628 regular-file bytes.
  The original Ruff checkout remains clean.
- Unmodified C composefs v1.0.8, `858ce1b38e1534c2602eb431124b5dca706bc746`.
  Native EROFS + overlayfs mount, **not FUSE**; fs-verity is not enabled.
- Kernel `7.0.0-30-generic`; backing filesystem ext4 on `/dev/nvme0n1p2`.
  These are plain backing directories, not Dagger's mounted overlay mirror.
- Go 1.26.6, CGO disabled. Tools compiled in the same Bookworm runtime as tests.
  Container image: `sha256:82150a52ec202c1b14d7817e14516c392bb7f5cfebd88f1ed531cb37ebd39922`.
- One temporary, network-disabled private mount namespace; no new Dagger engine,
  background worker, package installation, or global cache clearing.
- Four alternating paired rounds with wcprof and detailed copier instrumentation;
  four further paired rounds with both disabled. Separate empty stores per arm
  and round. Each round retains its store across the seven tree states.

Cold means **empty CAS with source page cache warmed by shared manifest capture**.
Input capture is a full scan/hash, separately reported, not the real filesync
client protocol. Source scanning, synchronization, snapshot registration, engine
provisioning and CLI overhead are outside the comparison.

## Uninstrumented confirmation: four samples per arm per row

All times are milliseconds. Medians of the measured quantities, not sums of
phase medians. The last column is the median of paired savings, so it need not
equal the difference between the displayed medians.

| Tree state | CAS ready | composefs ready | CAS ready + first read + release | composefs ready + first read + release | Paired saving, positive is faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Empty CAS | 938.68 | 913.36 | 1236.41 | 1377.95 | -142.88 |
| Unchanged, forced rematerialization | 371.51 | 145.36 | 681.00 | 606.09 | 76.69 |
| One-file edit | 363.60 | 145.92 | 666.21 | 607.91 | 56.01 |
| Move directory into new subdirectory | 363.48 | 145.80 | 668.25 | 605.08 | 63.17 |
| Mixed: 128 edits, 64 additions, 64 deletions | 385.03 | 159.72 | 683.19 | 616.29 | 64.12 |
| Broad reorganization | 369.72 | 148.64 | 672.50 | 608.93 | 66.75 |
| Repeat edited tree, forced rematerialization | 372.15 | 147.39 | 680.64 | 612.99 | 67.81 |

Broad reorganization uses the existing matrix selector: 24 disjoint directory
moves/renames, 64 independent file moves, 32 additions and 32 deletions across
multiple crates/depths. Explicit mappings are preserved in `fixture-plans.json`.

The unchanged/repeat rows **force materialization**. Real filesync's complete
result cache normally skips both materializers: these are not no-op CLI results.

`first read` traverses every entry, reads and hashes all regular-file bytes, and
asserts semantic metadata. It is not a pure read syscall measurement or a Cargo
workload. The one-read sum adds unmount measured after the second verification
pass; it is a component sum, not an independently executed one-read workload.

All four warm pairs improved this component sum. One-file paired savings ranged
52.29–69.28 ms. All four cold pairs regressed, by 49.30–166.66 ms.

### Repeated consumption matters

| State | CAS ready + two full reads + release | composefs ready + two full reads + release | Paired saving |
| --- | ---: | ---: | ---: |
| Empty CAS | 1522.65 | 1701.80 | -181.07 |
| One-file edit | 955.93 | 931.10 | 27.66 |
| Mixed diff | 972.34 | 939.38 | 29.91 |
| Broad reorganization | 960.50 | 938.72 | 23.21 |

These are measured wall intervals. Repeated reads erode the materialization
benefit. No extrapolation to actual Rust compiler access patterns is validated.

## Where time moved: one-file edit

Uninstrumented phase medians (not additive medians):

| Work | CAS | composefs |
| --- | ---: | ---: |
| Full copier and synchronous admission | 363.55 | — |
| CAS lookup / missing-object admission | included above | 41.39 |
| Encode text metadata | — | 47.98 |
| Upstream image generation | — | 53.46 |
| Native mount | — | 3.24 |
| First full read + verification | 300.94 | 428.23 |
| Second full read + verification | 287.85 | 321.86 |
| Unmount | — | 30.87 |

Each one-file edit ingested exactly one new object in both arms. The resulting
composefs image was 2,797,568 bytes. The prototype still reconstructs the image
for the entire tree, but does not create another full directory hierarchy.

Cold composefs admission alone was 807.77 ms. It uses the same verified writer,
but without a result tree must temporarily stage and atomically publish each
missing backing file. No per-file fsync is added. A cold win is not demonstrated.

Cold admitted-object counts differ intentionally: 10,608 for CAS versus 10,550
for composefs. Empty files need no payload in composefs; independent equal files
can share bytes while retaining separate logical inodes. Both result trees pass
the same byte and alias checks.

## Validation and evidence

- 112 successful timed Ruff samples, two full byte/metadata reads each.
- All 56 diagnostic wcprof profiles analyzed: zero dropped events, zero open
  operations at dump, one root, 0.0% replay drift.
- Maintained analyzer checkout: `e9da88e4fe7033bb213e4a84f30110a1187dd25b`.
- Twelve focused top-level CAS/escaping regression tests passed, including
  content-change rejection, xattrs, metadata and alias preservation.
- Tiny two-arm fixtures passed: empty files/directories, spaces/newline in names,
  dangling and valid symlinks, genuine aliases and independent identical files.
- Temporary containers and mounts removed after each run. CAS/results retained;
  no other engines or volumes stopped or removed for this experiment.

Evidence root: `/tmp/dagger-filesync-composefs.Qka67U5x`.

```text
run.py                              local runner, reuses frozen fixture selectors
matrix-r1/results.json              all profiled samples, outputs and phase timings
matrix-r1/analysis/                 all 56 wcprof reports
matrix-r1/fixture-plans.json        exact mixed/reorganization path mappings
matrix-unprofiled-r1/results.json   all confirmation samples including release
unit-tests.log                     focused regression log
smoke-r*/                          earlier smoke failures and successful retries
host-before.txt / host-after.txt   host container activity snapshots
```

Raw result SHA256:

```text
profiled:   c296afe9ebb474bcd8553cf7fd7e52daa21ef87099e118e431bfaae98367089f
unprofiled: 1c6f7676accdbf4893bcb4ae736e6886be0372aecc427dd14b29e17085f52703
```

The first cohort deferred unmount to test cleanup, visible in wcprof parent
self-time. The confirmation adds an explicit unmount phase; it does not omit or
subtract that cost. No old cohort is rewritten. A read-only directory-size
inspection occurred during the first cohort, so use the uninstrumented
confirmation for latency conclusions. Host snapshots are not continuous proof
of zero external activity; this is a bounded local experiment, not a universal
performance claim.

The initial C FUSE smoke failed backing-file lookup; the native path passed.
Another initial test correctly caught the wrapper-root metadata mismatch in the
verifier, and a tool build required matching Bookworm libc. Those failures are
retained, not counted as successful performance samples.

See [README.md](README.md) for exact opt-in test inputs, correctness boundaries,
and the snapshotter/GC work explicitly not undertaken by this branch.
