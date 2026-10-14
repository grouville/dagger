# Native snapshot checkpoint experiment

A checkpoint keeps the current immutable Directory snapshot independently of
the recipe that produced it. The Rust experiment checkpoints its returned cache
batches; the next compiler action still receives that Directory as an ordinary
explicit seed input. Compiler state stays in the engine as native snapshots.

The isolated engine adds an experimental Directory field and a private cached
value constructor. It pins the materialized snapshot under the new value's own
ownership. It rejects directories with services or session-resource requirements.
The Rust module uses an experimental query without regenerating SDK bindings.

On a fresh engine, twenty unique app edits preserve 3/4 compiler results.
Checks after pruning preserve 4/4. Captures wait for all sessions to release.

| After pruning | Without checkpoint, edit 20 | Checkpoint, edit 5 | Edit 10 | Edit 20 |
| --- | ---: | ---: | ---: | ---: |
| Latest cache's reachable results | 552 | 299 | 299 | 299 |
| Distinct snapshot references | 273 | 59 | 59 | 59 |

The checkpoint engine's initial closure is 285 results and 51 snapshot references.
Its cache accounting grows from 3,726,805,303 to 3,736,295,735 bytes after twenty
edits, including images and helper data. This is not unique filesystem-byte
accounting. Final hint eviction and full pruning remove all Rust compilation and
cache objects.

Seven focused tests pass under the race detector in a privileged local engine
container:

- The producer is collected while the checkpoint's files survive GC; final
  checkpoint release and pruning collect the checkpoint.
- Saved checkpoint state survives a cache-database restart.
- A transitive session-resource dependency is rejected.
- Native value transfer carries one Directory record and its snapshot chain,
  with no producer history, and the receiver reads the transferred file.
- Cancellation after snapshot pinning releases the new ownership.
- Concurrent requests publish the same checkpoint identity.
- Session-resource requirements added during pinning are rejected. This test
  fails before the second resource check and passes with it.

The real Rust module also passes its writer checks and transfers its cache to a
fresh engine. The receiver reuses 4/4 results, then reuses 3/4 after a new app edit,
including the transferred incremental state. The writer verifies plan refresh
after configuration and target changes, and rejection of unsupported build
scripts and invalid configuration.

Five alternating pairs of ordinary CLI checks on a 102-crate workspace give
these medians. Both variants use the same hardened engine. Each native command
has an untimed follow-up probe confirming all 102 published results are reusable.
Cargo rebuilds the expected two crates for each leaf edit and 102 for each shared
edit. Warm caches receive a new source edit on every timed command.

| Edited command | Without checkpoint | Checkpoint | Cargo, control tree | Cargo, checkpoint tree |
| --- | ---: | ---: | ---: | ---: |
| Leaf edit | 0.905 s | 0.842 s | 0.090 s | 0.089 s |
| Shared edit | 1.535 s | 1.450 s | 0.484 s | 0.506 s |

Four of five leaf pairs and three of five shared pairs improve. Maximum observed
I/O stall is 70.2%, with large Cargo outliers too, so this series does not establish
a latency improvement. All samples remain in the results. The retention bound is
the demonstrated benefit.

wcprof captures after timing contain no dropped events or unfinished operations.
The checkpoint variant makes six additional nested queries (100 to 106), one per
retained batch. Five checkpoint calls hit; the new batch takes about 48 ms,
principally content hashing. The private constructor itself takes under 1 ms.
Batching requests and reducing necessary hashing are concrete next experiments.

This remains an isolated prototype, not a selected implementation. The private
constructor can load an existing native value but cannot reconstruct missing
bytes from its recipe alone. The second resource check covers growth during
pinning; arbitrary resource changes after publication still require a lifecycle
argument before exposing a general API. The twenty-edit retention series used
the earlier prototype; the hardened branch passed the focused tests, real module
transfer and 102-crate command checks above.

Engine checkout: `/tmp/dagger-rust-snapshot-checkpoint`, commit `ef3698006`, based
on `350752bc2`. Rust module checkout: `/tmp/dagger-rust-module-checkpoint`, commit
`d1aaf93`, based on `7d5c1e8`. Both use branch
`experiment/native-snapshot-checkpoint`. Retention artifacts are under
`/tmp/rust-cache-sipsma-review/native-hint-checkpoint-retention`; paired command
results and profiles are under `module-checkpoint-102` in that review directory.
Focused race output is `checkpoint-final-race.log`; real module transfer logs are
`checkpoint-transfer-writer.log` and `checkpoint-transfer-reader.log`.

## Batching checkpoint requests

A separate Rust module experiment publishes all retained batches in one aliased
query, using the same Directory IDs and checkpoint calls. It preserves the
manifest's batch ordering and fails publication if a checkpoint is missing.
It changes no engine code or compiler inputs.

The actual module writer passes cold, normal-check, edit, revert, configuration
refresh and rejection checks. A receiver on a separate engine reads the
transferred cache fields, reuses 4/4 results, then reuses 3/4 after a new edit.
The writer uses a new project key: its first attempt reused an earlier default
project hint and returned 4/4 hits where the test expected a cold 0/4 result.

Five alternating pairs compare sequential and batched publication on the same
engine, with new leaf/shared edits, separate project histories and Cargo targets.
All 20 timed Cargo commands rebuild the expected two or 102 crates; all 20
untimed follow-up probes recover the normal CLI's published 102/102 results.

| Edited command median | Sequential requests | One request | Cargo, control tree | Cargo, batch tree |
| --- | ---: | ---: | ---: | ---: |
| Leaf | 0.855 s | 0.860 s | 0.088 s | 0.086 s |
| Shared | 1.383 s | 1.392 s | 0.476 s | 0.477 s |

Only two of five pairs improve in either scenario. Maximum observed CPU/I/O
stall is 32.9%/32.4%. This experiment establishes fewer requests, not a latency
improvement, and stays isolated.

Both wcprof captures have zero dropped events and no unfinished operations.
Nested requests fall from 106 to 101; all six checkpoint calls remain, with five
hits. New checkpoint work still takes about 49 ms. Directory copies remain
about 93–105 ms on the helper's critical path. Removing five round trips does
not remove those costs.

Rust branch:
[experiment/native-checkpoint-batch](https://github.com/grouville/dagger-rust/tree/experiment/native-checkpoint-batch),
commit `76f927b`. Artifacts are under
`/tmp/rust-cache-sipsma-review/module-checkpoint-batch-102`; the script is
`measure_checkpoint_batch_pairs.py`. Correctness logs are
`checkpoint-batch-transfer-writer-isolated.log` and
`checkpoint-batch-transfer-reader.log` in the same review directory.

## Inheriting include matches while copying

The next isolated engine experiment avoids scanning every include pattern for
every descendant of a directory that already matched. A positive include match
is inherited by the whole subtree. Negated include patterns still use the
existing matcher; explicit file selections, excludes and gitignore checks still
run for each entry. No filesystem metadata, hash format, cache key or locking
changes are involved.

The production change adds nine lines and removes four in
`util/layercopy/filter.go`. A focused test compares results with Moby's original
matcher for positive includes, excludes, explicit selections and negations.
The complete `util/layercopy` suite passes under the race detector.

Three benchmark repetitions use a precomputed descendant path, like the real
copier. These medians measure the filter alone, with no filesystem copying:

| Include patterns | Existing matcher | Inherited match | Existing allocation | Inherited allocation |
| --- | ---: | ---: | ---: | ---: |
| 1 | 81 ns | 69 ns | 1 B | 0 B |
| 16 | 200 ns | 66 ns | 16 B | 0 B |
| 128 | 960 ns | 67 ns | 128 B | 0 B |
| 1024 | 7,046 ns | 66 ns | 1,024 B | 0 B |

This establishes constant work after a positive ancestor match. It does not
establish a complete Rust command improvement. The candidate engine passes the
real module writer's cold/edit/revert and configuration checks. Its transfer
check exposed a separate baseline problem, so ordinary-command timing remains
pending.

### Restart mismatch found before timing

The receiver's initial transfer check reports 0/4 reused results. Configuration
and normalized compiler recipes agree with the writer; returned compatibility
keys agree too, but all four package-result keys differ. The compiler's grouped
package-digest query shows different hashes across the engines for identical
source files. Individual cached Directory digest calls hide that difference.

Restarting the unmodified control binary reproduces the same four grouped hash
changes and makes them match the candidate. The initial transferred build then
passes 4/4; its subsequent edit still reports 0/4 instead of 3/4. A grouped
original/edit diagnostic preserves unchanged library hashes on the restarted
control, while the candidate's previously cached edited view returns the earlier
hashes. This mixes cached and freshly scanned identities on the old engine base.

The benchmark base `ef3698006` does not include the separate native
hash-persistence fix. Next, integrate the reviewed persistence change into both
engine variants and repeat transfer, edit and restart checks before timing.
The copy-filter experiment stays isolated. Neither a general latency gain nor
end-to-end transfer correctness is claimed for it yet.

Engine checkout: `/tmp/dagger-rust-positive-copy-filter`, branch
`experiment/inherit-positive-copy-filter`. It runs on the owned receiver at
16271/16099, using that container's existing volume and runtime helpers. The
previous binary is backed up as `positive-filter-receiver-original-engine`.
Artifacts under `/tmp/rust-cache-sipsma-review` include
`positive-copy-filter-race.log`, `positive-copy-filter-bench-*-final.log`,
`positive-copy-filter-transfer-*.log`, `positive-copy-filter-grouped-*.log` and
`positive-copy-filter-control-restarted-digests.log`. The paired timing script
`measure_positive_copy_filter_pairs.py` is prepared but has not run.

## Comparison with persistent imported hashes

Both engine variants now include the reviewed native hash-persistence fix.
The control is `86c94a5d9` on `experiment/native-checkpoint-persistent`; the
candidate adds only the copy-filter change, `406295341d` on
`experiment/positive-copy-filter-persistent`. One merge conflict retained both
the newer owner-lease index and the hash-record restoration. Fresh volumes run
on 16272/16100 and 16273/16101; the two older volumes remain intact.

Focused native metadata and cache-persistence race tests pass, as does the full
layercopy race suite. The actual Rust module writer passes its cold/edit/revert
and configuration checks. Transfer to the fresh candidate reuses 4/4 results,
then 3/4 after an edit. Transfer and edit also pass after candidate restart.
Both engines preserve all eight grouped original/edit hashes across restart.
The candidate hash confirmation runs sequentially on a restored fixture: an
earlier comparison overlapped a source edit and is excluded from this evidence.

The outer experimental RustNativeCache object ID is not restored after restart.
Reconstructing it from its saved plan, manifest and native Directory fields
reuses 4/4 results; a new host edit then reuses 3/4. This verifies persisted
compiler state, not automatic cache discovery across engine restarts. That
remains part of the unfinished Rust module workflow.

Five alternating pairs measure new leaf/shared edits through the normal CLI,
with independent histories, Cargo targets and unique source edits. Telemetry
stays enabled locally and wcprof is off during timing. Every timed Cargo call
rebuilds the expected two or 102 crates; every untimed follow-up probe recovers
the CLI command's published 102/102 results.

| Edited-command median | Control | Copy-filter candidate | Cargo, control tree | Cargo, candidate tree |
| --- | ---: | ---: | ---: | ---: |
| Leaf | 0.879 s | 0.874 s | 0.094 s | 0.090 s |
| Shared | 1.448 s | 1.428 s | 0.483 s | 0.469 s |

Three leaf pairs and two shared pairs improve. Maximum CPU/I/O stall is
25.1%/29.3%. The small median changes do not establish a command-speed gain.
The filter microbenchmark's reduced work remains valid; keep this engine
experiment isolated pending stronger complete-command evidence.

Both subsequent wcprof captures contain zero dropped events and no unfinished
operations. Total copy work is 101.49 ms in the control and 120.77 ms in the
candidate. The candidate's critical path attributes only 12.03 ms directly to
copying because it instead waits 132.41 ms on snapshot ownership synchronization.
The holder spends 135.28 ms waiting for the lazy snapshot body; lease attachment
after that wait takes about 0.59 ms. These overlapping intervals must not be
added, and the apparent reduction in critical-path copy time is not work saved.
The optimization changes no locks. Removing this wait without preserving
snapshot ownership would not address the copy work it is waiting for.

Artifacts are under `/tmp/rust-cache-sipsma-review`:
`module-positive-copy-filter-persistent-102`,
`measure_positive_copy_filter_persistent_pairs.py`,
`checkpoint-persistent-*-transfer-*.log`,
`checkpoint-persistent-*-grouped-*-confirmation.log`,
`checkpoint-persistent-host-edit-*.log`, `checkpoint-persistent-race.log` and
`positive-copy-filter-persistent-race.log`. No new PR is opened.
