# Flat filesync inode-cache experiment

This is a measured experiment, not an upstream-ready performance fix.
Base: upstream main `523f3fe37b0d03f8fd7ee1aaa77b2ca0f1978b59`.

## Architecture

Keep the normal host scan, conflict tracking, semantic content hashes and exact
snapshot reuse. New mirrors separate host paths (`files/`) from sealed regular
files (`blobs/`). Each blob key combines an already-verified semantic file hash
with metadata/mtime; the existing Dagger semantic hash algorithm is unchanged.
Copy a missing inode, verify it and publish atomically; reuse existing layercopy
hardlink support to populate **parentless** result snapshots. No containerd fork,
authoritative CAS manifest hierarchy, per-object leases or per-file fsync.

The ordinary result snapshot remains authoritative. Removing a cache link does
not remove result links. Never link the writable mirror into a result. Cache
inodes are not modified after publication, including through hardlink aliases.
Equal independent files must not become hardlinks within one result. Legacy
persisted mirrors keep their old layout; new-layout mirrors persist a version.

This avoids a growing layer chain but still recreates the directory namespace.
It is not an O(changed paths) materializer or a host change-detection solution.

## First Ruff comparison

Ruff `c2cd236b9cc5b2149c74247e179d6567ec74066f`, 89,442,628 regular-file
bytes: 11,139 files, 885 directories and one symlink (12,025 entries).
One-file edit: `crates/ruff/src/lib.rs`.
Six alternating pairs, four flows per arm (48 profiled standalone commands),
fresh owned engine volume and CLI state per arm. Images already available;
host OS caches not cleared. Default GC, no observed evictions. Main and candidate
have matched CLIs, inputs and real novel edits. No Cargo/module E2E claim.

Native wcprof session.serveQuery union, milliseconds:

| Flow | Main median | Candidate median | Median paired difference |
| --- | ---: | ---: | ---: |
| Cold import | 2107.406 | 2708.730 | +577.491 |
| Unchanged | 365.572 | 350.052 | -2.364 |
| One-file edit | 1085.822 | 820.354 | -267.155 |
| Unchanged after edit | 366.465 | 352.127 | -21.399 |

Complete profiled CLI wall time, milliseconds:

| Flow | Main median | Candidate median | Median paired difference |
| --- | ---: | ---: | ---: |
| Cold import, including engine startup | 5324.968 | 6076.886 | +576.148 |
| Unchanged | 941.555 | 941.671 | -0.537 |
| One-file edit | 1717.303 | 1391.605 | -302.551 |
| Unchanged after edit | 966.269 | 915.908 | -50.863 |

All source/digest checks, profile completeness/replay gates and pair-one full
export parity passed. Every edited candidate import ingested exactly one blob;
unchanged imports ingested none. Candidate unchanged CLI max was 1568.336 ms
(main 1067.529 ms), retained, not removed. n=6 p95 is only the maximum.

Repro/evidence on this host:
`/tmp/dagger-filesync-flat.c5ihvUc6/{build.py,prepare_filesync_pairs.py,run_pairs.py}`
and `filesync-pairs-r1/{RESULTS.md,RESULTS.json}`. The receipts retain engine/CLI
hashes, complete source fingerprints, raw profiles, manifests, default-GC logs,
all timings and ownership-guarded engine shutdowns. No source modifications or
other heavy tests/builds ran during measurement. Original module and workspace
were untouched; fixtures and benchmark tooling are separate copies.

Focused checks passed with race detection using the supported containerized Go
module: `go test -tags=privileged -race -parallel=1 -count=1 ./engine/filesync`
(selected cached-file/source/hardlink/re-included-parent tests), and the complete
`./util/layercopy` package. Exact commands are in build-r2/build-r3 receipts.

## Corrected candidate: second independent cohort

Candidate `78408ba` includes the mixed-copy metadata fix (`f87d508`) and real
mutable-mirror size refresh (`78408ba`). Race-enabled layercopy, focused filesync,
and real-snapshot growth/deletion accounting regression tests passed (build-r5
through build-r7). Build-r8 exported this exact committed source.

The same six alternating pairs and 48 profiled commands passed source/digest,
profile completeness/replay and full edited-tree export gates. No observed
evictions. Do not pool the two cohorts: their candidate code differs.

| Flow | Main engine median ms | Candidate engine median ms | Median paired candidate−main ms |
| --- | ---: | ---: | ---: |
| Cold import | 2120.474 | 2720.031 | +579.534 |
| Unchanged | 390.210 | 368.971 | +9.008 |
| One-file edit | 1110.835 | 844.485 | -241.061 |
| Unchanged after edit | 358.500 | 371.258 | +9.618 |

| Flow | Main CLI median ms | Candidate CLI median ms | Median paired candidate−main ms |
| --- | ---: | ---: | ---: |
| Cold import, including engine startup | 5351.307 | 5977.142 | +574.247 |
| Unchanged | 996.485 | 965.572 | -55.466 |
| One-file edit | 1717.550 | 1516.939 | -175.127 |
| Unchanged after edit | 916.690 | 966.183 | -0.701 |

The candidate edit engine range was 821.493–2130.464 ms and CLI range
1416.330–7609.446 ms, versus main 1071.265–1162.418 and 1667.071–1918.411 ms.
Both slow candidate samples remain in the report. Elevated host I/O pressure
coincided with the largest CLI tail; that is not a demonstrated cause. Median
paired differences need not equal the difference of the two marginal medians.

Evidence: `/tmp/dagger-filesync-flat.c5ihvUc6/filesync-pairs-r2/RESULTS.md` and
`RESULTS.json`; root `BREAKDOWN.md` explains phase boundaries and remaining
attribution gaps. These are profiled diagnostics, not unprofiled performance
proof. The candidate has many more native profiling events than main.

## Promotion blockers

- Cold import is slower. Do not advertise an across-the-board win.
- Bound/evict the inode cache and validate long-running default-GC behavior.
- Attribute and resolve edited-command tails; do not discard them as noise.
- Validate restart/layout migration, concurrent imports and real writable
  container isolation. Unit hardlink isolation tests are not all these gates.
- Account shared physical bytes accurately; standalone snapshots must not depend
  on retaining the cache for their data lifetime.

The first scorecard above remains the initial prototype, before follow-up fixes.
