# Mounting native incremental state directly

The isolated Rust module branch mounts incremental state separately from its
artifact/marker snapshot. It starts from the largest compatible seed snapshot
and overlays only the selected crates from other snapshots. Crates without
a compatible seed start empty. This removes a full incremental-tree copy;
both outputs remain immutable native Dagger directories.

The public cache API stays manifest/tokens/snapshots. Format 2 adds a mapping
from artifact-batch tokens to incremental-snapshot tokens. The reader accepts
format 1 combined snapshots, and compiler-result identities continue using
the original algorithm version. Old readers reject format 2 rather than
mistaking its artifact snapshot for incremental state. Validation rejects
missing, aliased, ambiguous and unreferenced state snapshots.

## Verification

- Backend unit packages pass: model, replay, worker and cmd/wrapper.
- Actual module cold build: 0/102 hits.
- Leaf and shared edits: expected 100/102 and 0/102 hits.
- Breaking shared-library type: compilation fails without publishing metadata.
- Four-crate Directory edit and reversion: 3/4 and 4/4 hits.
- Normal check entrypoint passes with a configured plan and native cache.
- Export/import on a fresh engine: 4/4 hits, then a new edit gives 3/4.

The transfer carries actual native directories, not engine-local numeric IDs.
No source or seed input is excluded from the execution cache key. The largest
seed snapshot may also contain unrelated crates' state, which affects execution
identity and retention; per-crate exact-result lookup remains separate.

## Measurements

The first five-pair series has heavy contention, including an 8.58-second
Cargo shared edit. It cannot establish a speedup. Its profiles show state-copy
critical time at 104.7 ms in the control and 41.1 ms in the experiment. However,
the extra native references increase session queries from 87 to 122, and the
two native-check critical paths are both about 1.19 seconds.

The helper then retains IDs already resolved from its input snapshot objects,
avoiding queries when returning those same snapshots. This reduces its profile
query count from 122 to 112. The selected snapshots and compiler identities
are unchanged. New output snapshots are still resolved normally.

Five further pairs use independent source trees, Cargo target directories and
native histories, unique edits, four preparation rounds and a failure tripwire.
Every timed Cargo rebuild set and native cache count matches the fixture.
Telemetry remains enabled to the local receiver; wcprof is off during timing.

| Edited command median | Control | Separate state plus retained IDs |
| --- | ---: | ---: |
| Leaf | 1.004 s | 1.036 s |
| Leaf Cargo | 0.091 s | 0.088 s |
| Shared | 1.510 s | 1.451 s |
| Shared Cargo | 0.503 s | 0.467 s |

The candidate includes an 8.014-second leaf outlier; no sample is discarded.
Maximum CPU/I/O pressure is 31.3%/5.2%. The overlapping samples and different
Cargo medians limit attribution. The shared median improves by 59 ms, while
the leaf median worsens by 33 ms. Keep this as an experiment, not a general
performance improvement.

One final shared profile has 43.8 ms of state copying, 164.4 ms of query
handling and 106.7 ms in the Rust module itself. Further work should reduce
snapshot-reference round trips and query work before selecting this layout.
Storage/transfer size, automatic plan/cache discovery and normal user workflow
remain unfinished.

Branch: [experiment/native-incremental-mounts](https://github.com/grouville/dagger-rust/tree/experiment/native-incremental-mounts).
Artifacts under /tmp/rust-cache-sipsma-review:

- incremental-mount-102-cold.log and incremental-mount-final-unit.log.
- incremental-mount-transfer-{writer,reader}.log and the final transfer logs.
- module-native-102-incremental-mounts: original series and profiles.
- module-native-102-incremental-mounts-known-ids: final series and profiles.
- measure_native_102_incremental_mounts_known_ids.py: local reproduction harness.

## Materialized-ID follow-up

An isolated prototype retains Directory/File IDs when decoding module inputs,
and returns already resolved output handles without querying their IDs again.
Its generated bindings are hand-edited; the output helper round-trips through
JSON. This is diagnostic code, not a finished SDK change. A general change
would need generator coverage and an explicit distinction between resolved
handles and recipe IDs that must still be evaluated.

Five alternating pairs again use independent sources, Cargo targets and native
histories. The control uses combined snapshots; the candidate includes separate
incremental mounts and the ID prototype, so these command timings do not isolate
the ID change. All 20 Cargo rebuild sets match the expected 2 or 102 crates;
native hit counts and the failed-compilation publication tripwire pass.

| Edited command median | Control | Separate state plus ID prototype |
| --- | ---: | ---: |
| Leaf | 0.971 s | 0.981 s |
| Leaf Cargo | 0.091 s | 0.090 s |
| Shared | 1.475 s | 1.390 s |
| Shared Cargo | 0.496 s | 0.466 s |

Four of five leaf pairs and three of five shared pairs improve, despite the
leaf median worsening by 11 ms. Maximum timed CPU/I/O pressure is 25.2%/21.6%.
These mixed results do not establish a general command improvement.

Both candidate profiles now have 86 session requests, versus 87 in the control;
the earlier split-state version had 112. All four captures have zero dropped
events. The shared profile attributes 10.7 ms to copying, versus 112.1 ms in
the control, but query handling remains 161.2 ms and the Rust module's own
critical-path contribution is 107.8 ms. Preserve the prototype for investigation
before selecting this layout or changing generated SDK behavior.

Artifacts: `module-native-102-materialized-ids` and
`measure_native_102_materialized_ids.py` under `/tmp/rust-cache-sipsma-review`.

## What fresh-process startup still costs

The four new profiles run on the same crun engine with warm images and cache,
fresh CLI sessions, edited sources, and fresh helper/worker processes. The two
runtime starts together take 19.3, 21.9, 22.4 and 27.3 ms. These are per-profile
totals for both starts, not individual-container times. Init and command spawn
are recorded separately: normally another 6–10 ms combined here, with one
shared capture at 18.5 ms. Filesystem and mount preparation are also separate.

The older roughly 90 ms runtime total came from runc. The crun comparison in
[NATIVE_PROFILE_FOLLOWUP.md](NATIVE_PROFILE_FOLLOWUP.md) already reduced that
phase substantially and measured a 41.5 ms complete-command median reduction.
Further runtime tuning can help, but removing the remaining runtime-start cost
would save only about 20–30 ms in these captures. It cannot explain the current
gap to Cargo on its own.

Keep fresh rustc processes while reducing snapshot preparation and repeated API
requests. The worker already batches changed crates into one container. Moving
the helper's graph orchestration into the existing module runtime could remove
another container plus its own work, but that needs an implementation experiment
and a complexity assessment. A persistent worker would add filesystem reset,
cancellation and lifetime management; the profiles do not yet justify making
that the default design.
