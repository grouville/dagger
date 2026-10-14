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

Four focused tests pass in a privileged local engine container:

- The producer is collected while the checkpoint's files survive GC; final
  checkpoint release and pruning collect the checkpoint.
- Saved checkpoint state survives a cache-database restart.
- A transitive session-resource dependency is rejected.
- Native value transfer carries one Directory record and its snapshot chain,
  with no producer history, and the receiver reads the transferred file.

This remains an uncommitted prototype, not a selected implementation. The private
constructor can load an existing native value but cannot reconstruct missing
bytes from its recipe alone. Late changes to resource requirements, cancellation,
concurrent publication and adoption require adversarial review. The extra digest
and per-batch query costs need complete edited-command measurements. Real Rust
module transfer also still needs validation for this checkpoint branch.

Engine checkout: `/tmp/dagger-rust-snapshot-checkpoint`, based on `350752bc2`.
Rust module checkout: `/tmp/dagger-rust-module-checkpoint`, based on `7d5c1e8`.
Both use branch `experiment/native-snapshot-checkpoint`. Artifacts are under
`/tmp/rust-cache-sipsma-review/native-hint-checkpoint-retention`; focused test
output is `checkpoint-privileged-tests-final.log` in that review directory.
