# Btrfs delta experiment — 2026-09-17

The delta implementation avoids full-tree reconstruction and reaches tens of
milliseconds for warm one-file materialization. **It is not a 40 ms Dagger
import or a Cargo speedup.** A new snapshot still has a costly first full read.
Production integration is not implemented. No perf-prod promotion is claimed.

## Setup

- Baseline: experimental synchronous result-first inode CAS, composefs branch
  checkpoint `4e7b0832`, not Dagger main.
- Ruff `c2cd236b9cc5b2149c74247e179d6567ec74066f`, same frozen fixtures as the
  composefs comparison: 12,026 nodes including root, 89,442,628 regular-file
  bytes initially. Originals and official Rust module untouched.
- Kernel `7.0.0-30-generic`, Go 1.26.6, btrfs-progs 6.2 in disposable Bookworm
  container. No host package install, repartitioning or kernel setting changes.
- Delta storage: new 8 GiB sparse Btrfs image file; CAS-Btrfs control: separate
  new 6 GiB image. Both loop-mounted over the same host ext4/NVMe backing as the
  plain CAS baseline. Default Btrfs checksums/COW; metadata DUP. No nodatacow,
  unsafe transaction settings, forced global cache eviction or background work.
- Each round starts empty stores; stores/results survive subsequent cases.
  All previous versions remain retained. No snapshot cleanup in timed samples.
- One isolated profiled round and four alternating unprofiled paired rounds.
  Other pre-existing containers were left untouched; exclusive host use is not
  claimed. Raw samples and earlier failed/confounded attempts remain retained.

## Unprofiled results, four samples per arm per row

Median milliseconds. These are measured per-sample totals, not sums of phase
medians. `ready` includes manifest comparison, snapshot, delta application and
read-only finalization, but excludes capture of the input manifests.

| State | CAS ext4 ready | CAS Btrfs ready | Btrfs delta ready | CAS ext4 ready + first full read | Btrfs delta ready + first full read |
| --- | ---: | ---: | ---: | ---: | ---: |
| Empty store | 919.05 | 1048.72 | 892.24 | 1105.49 | 1094.52 |
| Unchanged, forced new result | 353.88 | 386.56 | 52.43 | 540.92 | 470.21 |
| One-file edit | 351.75 | 385.79 | 40.24 | 538.29 | 450.73 |
| Move directory into subdirectory | 359.94 | 384.80 | 42.68 | 547.23 | 483.29 |
| Mixed: edits/additions/deletions | 360.23 | 404.30 | 71.26 | 545.79 | 482.29 |
| Broad reorganization | 356.63 | 388.59 | 103.72 | 544.55 | 503.22 |
| Revisit edited tree after reorganization | 353.86 | 384.52 | 91.03 | 539.69 | 489.31 |

Mixed fixture contains 128 modifications, 64 additions and 64 deletions relative
to original; broad reorganization contains 24 directory moves, 64 independent
file moves, 32 additions and 32 deletions. The sequence traverses these states,
so a delta also reverses differences from the immediately preceding state.
The simple directory-move fixture is small, not the broad-rename worst case.

Preparation improves 8.7x for the one-file edit; consumer-inclusive improvement
is about 16%. First full reads remain slower on new Btrfs snapshots. A second
read is faster, but is not substituted for the first. These verifiers read/hash
the whole tree; no Rust compiler access pattern has been measured here.

Cold is effectively tied consumer-inclusively in this small sample, not a
demonstrated major cold-start win. The delta arm does not publish separate CAS
objects, so the arms also differ in cross-tree deduplication capabilities.

## One-file attribution

| Phase | Btrfs delta median ms |
| --- | ---: |
| Compare supplied manifests in memory | 13.83 |
| Create writable successor snapshot | 17.49 |
| Apply verified file/ancestor changes | 0.57 |
| Make successor read-only | 8.17 |
| Ready total | 40.24 |
| First full read/verification | 412.28 |
| Second full read/verification | 172.09 |
| Recheck previous version (correctness gate) | 172.49 |

One-file ready samples: 37.34, 40.93, 39.55, 50.76 ms (rounded); paired savings
versus CAS-ext4: 317.33, 304.30, 313.34, 299.85 ms. The median is not a tail
guarantee. Copying the changed bytes is now a small fraction of the cost.

The Btrfs arm's common input capture also scans the previous tree (median
348.52 ms total capture). It stands in for retained manifests; it is excluded
explicitly, not represented as eliminated production work. Actual host discovery,
canonical root hashing, RPC, engine ownership and CLI startup remain out of scope.

## Earlier diagnostic and tooling failure

`profile-r1` stopped exporting profiles because `docker cp` could not see the
container-private nested Btrfs mount. Streaming with `docker exec cat` fixed
the harness. The raw partial cohort remains.

`profile-r2` put both Btrfs arms on one filesystem. One-file snapshot creation
took 110.69 ms and total preparation 138.20 ms. With independent filesystems,
the profiled one-file preparation was 31.15 ms. The shared-filesystem case is
retained as evidence that unrelated metadata writes/transactions can affect
latency. Production contention on a shared engine still needs its own test.

## Evidence

Root: `/tmp/dagger-filesync-btrfs.2gaOIzH6`.

```text
setup.log, setup-control.log    exact filesystem properties and backing devices
provision.log                  container-only tool installation
profile-isolated/              21 successful profiled matrix samples
matrix-isolated/               84 successful unprofiled matrix samples
profile-r1/, profile-r2/        incomplete/confounded diagnostics, preserved
sequence128/                   long retained-history experiment
filesystem.img, control.img    retained Btrfs filesystems
```

## Retained history: 128 consecutive edits

All 128 edit steps passed, each writing exactly one regular file and verifying
the predecessor after creating its successor. All 129 snapshots (including the
initial import) remained retained; there was no flattening or layer compaction.

Preparation: median 37.64 ms, empirical p95 50.03 ms (floor-index quantile),
maximum 59.63 ms. First 32 edits: median 33.33 ms; last 32: 39.30 ms. This is
evidence against an overlay-style layer-depth problem over this tested history,
not proof of unlimited snapshots or constant cost under arbitrary contention.
Half the edits target one file repeatedly; half target distinct source files.

See README.md for invariants, reproduction, limits, and the separate engine
integration work. The user requested that follow-up: this benchmark checkpoint
must not be confused with a complete Btrfs engine/delta implementation.
