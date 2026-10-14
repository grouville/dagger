# Avoid a second filesystem scan when retaining native compiler state

The native Rust build/test profile identifies 53 ms inside `Directory.checkpoint`
on a warm edited test command. That prototype creates an independently owned
immutable snapshot value by hashing the completed directory, then pinning its
snapshot. The scan is an identity choice rather than an ownership requirement.

An isolated experiment adds `checkpoint(snapshotIdentity: true)`. It uses the
committed snapshot identity, directory path and platform instead of reading the
directory to derive a content digest. It still evaluates the source, rejects
session resources and services, pins the snapshot independently, and rechecks
the resource guard after pinning. No compiler inputs are ignored and rustc state
remains native immutable Dagger cache.

The tradeoff is less deduplication at checkpoint creation: separately created
snapshots with identical bytes remain distinct checkpoint values. Existing
content-based checkpointing stays available. Local snapshot identity is used to
construct a closed value; native transfer carries the materialized snapshot
through the existing snapshot links. It does not make local snapshot names into
a remote compiler-cache lookup key.

## Verification

- The focused checkpoint suite passes under the race detector for both modes:
  producer release, pruning, clean restart, native transfer without producer
  history, cancellation, concurrent publication, and resource growth while
  pinning. Two added tests verify that snapshot-mode creation does not mount
  contents and that different snapshots and subpaths do not alias.
- Actual native Rust tests pass cold capture, custom harness filesystem effects,
  runtime-only edits with complete compiler reuse, runtime test failures,
  documentation test failures and valid restoration.
- Actual module cache discovery survives a clean restart of the candidate
  engine: tests reuse 5/5 actions and development builds 4/4. Subsequent edits
  reuse 2/5 and 3/4, and ordinary test/generation commands pass.

Explicit Rust cache transfer also passes from the new mode to the unchanged
control engine. All five test compiler results reuse; a new application edit
reuses 2/5. A runtime-only data edit fails execution and valid restoration
passes. This verifies portable compiler snapshot fields, not remote lookup
or transfer performance.

Twenty edited native test builds retain a stable pruned closure of 332 results
and 79 snapshot references at edits 5, 10 and 20. All five compiler results
reuse after each prune. No mutual ownership pair is found, and prototype hint
eviction followed by pruning releases every Rust cache object. This establishes
bounded graph retention for the fixture, not unique physical storage bounds.

## Measurement boundary

The initial eight-pair test-command comparison is noisy: I/O pressure peaks at
50.5%, and one Cargo control rises from approximately 0.35 s to 1.41 s. Its
medians, 1.104 s for content checkpointing and 1.349 s for snapshot identity,
cannot establish a useful speedup or regression. All samples are retained.

Both separate diagnostic captures have zero dropped events and zero unfinished
operations. The content mode spends about 56 ms on the checkpoint critical path;
snapshot mode removes that scan. This capture alone does not establish full
command benefit, including any work moved into subsequent input preparation.

A separate twelve-pair test series gives medians of 1.092 s and 1.024 s,
with 11/12 pairs faster. Two early rounds still encounter high I/O pressure
(the maximum is 55.4%), so the 68 ms difference is provisional. Later profiles
record 859 ms versus 808 ms on the check critical path: compiler/test workload
is similar, while the approximately 54 ms checkpoint scan disappears.

The 102-action workspace comparison alternates eight shared edits and eight
leaf edits through ordinary `dagger check rust:check`. Each variant has separate
source trees, project keys and native Cargo targets on the same candidate engine.
Three preparation edits precede timing. Cargo logs confirm 102 rebuilt crates
for a shared edit and two for a leaf edit. Untimed probes confirm every native
compiler result is reusable after each normal command. Telemetry stays enabled;
wcprof is captured separately after timing.

| Edited command, median | Content checkpoint | Snapshot identity | Cargo control |
| --- | ---: | ---: | ---: |
| Shared edit, 102 actions | 1.443 s | 1.385 s | 0.476 / 0.473 s |
| Leaf edit | 0.862 s | 0.869 s | 0.088 / 0.089 s |

All eight shared-edit pairs improve; only three leaf pairs do. There is no
established leaf-edit gain. Timed CPU pressure peaks at 31.3%, and I/O pressure
at 24.1% in a Cargo leaf control. The paired shared result and removed critical
scan support the experiment, while the host conditions limit precision.
The candidate still exceeds the Cargo +0.5-second target.

The full Rust cache objective remains open. Registry dependencies, build scripts,
procedural macros, remote state discovery, crash durability and edited complete
commands within Cargo +0.5 seconds remain unfinished.

Engine branch: [experiment/native-checkpoint-snapshot-key](https://github.com/grouville/dagger/tree/experiment/native-checkpoint-snapshot-key).
Module branch: [experiment/native-checkpoint-snapshot-key](https://github.com/grouville/dagger-rust/tree/experiment/native-checkpoint-snapshot-key).
Engine commit: `1770e627a`. Module commit: `7d5c1a4`.
This remains an isolated fork experiment; no upstream PR is opened.
Local artifacts are under `/tmp/rust-cache-sipsma-review`:
`checkpoint-snapshot-key-tests-reviewed.log`, `snapshot-key-test-retention`, `snapshot-key-native-tests`,
`snapshot-key-build-test-restart`, `native-test-checkpoint-key-paired`,
`native-test-checkpoint-key-confirmation-confirmation`, and
`module-checkpoint-snapshot-key-102`.
