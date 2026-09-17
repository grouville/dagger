# Async admission: resumed comparison

The earlier filesync-pairs-r2 is retained unchanged as an incomplete diagnostic.
It overlapped the user's other experiment. Runtime47's cold capture passed
source/digest and native replay gates but failed the old CLI-only interval
gate: optional admission finished 93.801 ms after CLI exit. That observation
is not silently relabeled as an accepted result.

## New, separate capture contract

profile_async.py is a sibling of the frozen profile_import.py. It leaves the
CLI stopwatch at process exit. profile_windows.py retains every native event,
peeks with flush=0 until explicit admission completes, then analyzes the full
dump. Only independent filesync.filecache.background roots and their known
publication descendants may extend past CLI exit, bounded to ten seconds of
event time. Foreground work remains inside the original CLI window; drops,
open operations, unrelated late work and replay drift still reject a capture.

The native tail after query and after CLI is reported separately. A background
failure is retained as a diagnostic outcome, not called successful admission.
This validation-separated series does not prove immediate-next-request
behavior or sustained throughput. Individual debug commands have a separate
30-second timeout; the ten-second bound is not a wall-clock harness timeout.

## Frozen comparison

filesync-async-matrix-r1 uses six position-balanced rounds, 18 fresh owned
engine/cache volumes, 13 flows per engine (234 profiled captures planned).

| Arm | Source | Seed image |
| --- | --- | --- |
| Main + common diagnostics/reserve-floor fix | c4512cf1 | runtime-r6 |
| Same + xattr opt-out + synchronous result-first CAS | 31064758 | runtime-r8 |
| Same CAS + asynchronous admission | 79a5f080 | runtime-r45 |

Main is pinned 523f3fe3, not freshly fetched pristine upstream. Images and host
OS page caches are available; 'cold' means new engine volume and CLI XDG state,
not a first installation or cold host disk. No Cargo/module speedup is claimed.

Existing cold, unchanged, one-file edit, directory move and restoration remain.
Two distinct additional cases are measured independently:

1. Mixed content: 128 modifications, 64 additions, 64 deletions.
2. Broad namespace reorganization: 24 disjoint directory renames/moves,
   64 independent cross-parent file renames, 32 deletions, 32 additions.
   On Ruff this spans six directory depths and touches 372 existing files
   (~2.39 MB); the per-run journal records exact mappings and byte counts.

Each has a repeat and a restoration import. The engine mirror is restored
between cases, so the reorganization is not accidentally combined with the
inverse of the mixed content diff. First-round full tree readbacks cover edited,
moved, mixed and reorganized trees on all three arms. All source manifests,
mtimes, output digests, owner identities, pressure and outliers are retained.

## Reproduce

```sh
python3 matrix_async.py prepare --cohort 1 --first-attempt 58
python3 matrix_async.py run --cohort 1
python3 summarize_async_matrix.py --cohort 1 --write
```

Existing directories are never overwritten; a rerun needs unused cohort/runtime
numbers. Fixtures restore through identity-checked journals; engines stop via
ownership receipts without deleting volumes. The owned official Rust module
and the user's main checkout remain untouched.

Unit/preflight verification before this run: 20 Python tests passed; the broad
case applied and restored the actual owned Ruff tree, with clean git status.
The candidate's privileged filesync race suite previously passed three times.

Production gate remains: the existing immutable Mount helper creates a view
lease without expiration. Normal shutdown releases it, but crash/restart
reclamation needs a fix/test before upstream promotion. Full writable-snapshot
isolation, GC during admission and immediate next-import overlap also remain.
