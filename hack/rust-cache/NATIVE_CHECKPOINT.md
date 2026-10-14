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
