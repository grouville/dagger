# Native cache through the Rust module

The Rust module now drives the extracted native replay backend. Compiler
outputs and rustc incremental state remain immutable Dagger directories,
retained alongside a manifest and batch tokens. The supported fixture is a
locked workspace with four path-only crates and 128 source files in its app.

## Edited-command measurements

Five pairs alternate the original integration and the optimized integration
on one engine. Every timed command changes the app's source. Each variant
gets a unique edit to prevent the shared engine from reusing the other
variant's worker execution. Four preparation edits fill the bounded history;
an invalid-source tripwire verifies failure without publishing a new cache.
One more preparation edit advances the history after that tripwire, so timed
constructor calls do not get an incidental hit from its inputs.

| Complete command, median | Original | Optimized |
| --- | ---: | ---: |
| Native Rust module | 1.154 s | 0.845 s |
| Native Cargo check | 0.174 s | 0.174 s |
| Module range | 1.138–1.181 s | 0.839–0.888 s |

All ten commands pass and reuse three of four compiler actions. The median
reduction is 310 ms, about 27%; every pair improves. Each command opens a new
client and imports a real host edit. Toolchain, filesystem and engine caches
are warm. Telemetry stays enabled through the isolated local receiver; wcprof
is disabled during timing. Host-wide CPU pressure stays below 3.2% during the
timed commands; maximum I/O pressure is 12.5%.

The command uses `dagger api with-session` and a small driver that calls the
actual Rust module. It includes client setup/close, module loading, source
import, compilation and result/cache materialization. It does not establish
the completed ordinary `dagger check` workflow, automatic plan/cache discovery,
or production Cloud/remote-engine latency. Cargo runs the same `check` mode
with Rust 1.77.2 and incremental compilation enabled.

The change removes a Go runtime invocation that only constructed the helper's
cache object, passes the cache fields directly to compilation, and selects
the result fields together. It also accepts the previous native cache object
as a check argument, keeping the Rust constructor stable across source edits.
Compiler inputs and cache keys are preserved.

Separate wcprof captures confirm that the helper's `restore` invocation
disappears. The remaining longest query still includes about 107 ms in the
Rust function itself, 62 ms of source-import work across the command, and
40 ms of helper runtime startup. The helper workload contains the nested
compiler execution; their durations overlap and must not be added.

Raw paired samples and pressure readings are in
`/tmp/rust-cache-sipsma-review/module-native-paired`. Separate profiles are in
`module-native-profile`, `module-native-profile-after-fields`, and
`module-native-profile-direct-object` under the same directory.

## Cache correctness and transfer

The actual module passes cold compilation, a native Directory edit with
three of four hits, reversion with four hits, native field export/import on
a separate receiver, and another edited compilation there with three hits.
The model, replay, worker and wrapper packages pass their unit tests.
Transferred cache fields are portable; the driver's local cache object IDs
are only handles for the engine retaining them.

The Directory-edit test exposed a separate engine bug: `withNewFile` created
a child snapshot without carrying over imported hash records. Checksumming
an untouched library then rescanned it using SHA-256 instead of its imported
XXH3 records, changing its digest and losing its exact compiler-result hit.
The scoped fix preserves those records and invalidates the written path.
It does not change the filesync hash formatter.

The standalone regression fails on upstream main without the patch and passes
with it. Coverage includes newly created directories, symlink writes, projected
directories, hard-link copy-up behavior, partial hash contexts, saved records
after LRU removal, and concurrent child contexts under the race detector.

On 20,000 imported files, two alternating engine series of five writes each
measure snapshot write plus unchanged-subdirectory digest at 651 ms median
on main and 11 ms with the patch. All ten unchanged digests change on main;
all ten stay stable with the fix. The write alone rises from 3.44 to 8.05 ms,
because it saves the inherited records, while digest lookup falls from 647 to
2.57 ms. This is a synthetic mutation/hash measurement, not a Rust build
speedup. Saving a full record tree on each write has a cost proportional to
the number of records; repeated writes to very large trees still need study.

The standalone branch is
[`fix/preserve-imported-hashes-on-file-write`](https://github.com/grouville/dagger/tree/fix/preserve-imported-hashes-on-file-write).
The module branch is
[`experiment/native-compiler-cache`](https://github.com/grouville/dagger-rust/tree/experiment/native-compiler-cache).

## Next measurements

Continue with CPU profiles and wcprof across CLI/module loading, source
imports, graph construction, snapshot preparation, runtime startup, compilation,
and telemetry. The native module still exceeds Cargo by about 0.67 s in this
fixture, above the 0.5 s target. Measure shared-library edits and many-crate
workspaces through the module, then finish automatic discovery and the normal
check workflow. Cache reference pruning does not yet prove bounded physical
snapshot ancestry or transferred storage size.

Sipsma's current PRs include the merged
[parsing reduction #14649](https://github.com/dagger/dagger/pull/14649) already in
the measured engine, the
[ordered logging queue #14653](https://github.com/dagger/dagger/pull/14653),
[session-helper cleanup #14655](https://github.com/dagger/dagger/pull/14655),
and the open
[unused BuildKit cleanup #14654](https://github.com/dagger/dagger/pull/14654).
The logging queue is another
candidate for edited-build measurements; its reported edited-build benefit is
suggestive, so do not assume it improves this workload before testing it.

The [follow-up profile](NATIVE_PROFILE_FOLLOWUP.md) narrows graph construction
to about 14 ms in the small fixture and evaluates a telemetry metadata decoding
experiment. The converter improves, but the matched command-level measurement
does not establish a latency win, so it remains an isolated experiment.
