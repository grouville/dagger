# Many-crate builds through the native Rust module

The real Rust module now runs the 102-action fanout fixture: one shared
library, 100 leaf libraries and an application. All checks use Rust 1.77.2
and Cargo check with incremental compilation. Compiler outputs and rustc
incremental state remain native Dagger objects. The engine includes crun,
nonblocking nested sessions and the scoped imported-hash mutation fix.

The integration driver's check stage accepts explicit expected action and
reuse counts. It validates them before saving cache metadata. Cold capture
and compilation report 0/102 hits. A leaf edit must reuse 100 actions; a
shared edit must reuse none. Changing the shared library's return type to
String makes dependent compilations fail without publishing cache metadata.

## Baseline and critical path

Five fresh edits per scenario give these complete command medians:

| Edit | Native module | Native Cargo |
| --- | ---: | ---: |
| Leaf | 950 ms | 88 ms |
| Shared library | 1,422 ms | 517 ms |

The initial leaf Cargo trial also rebuilds the shared library after the
invalid-type tripwire restores its timestamp; the other four rebuild only
the leaf and application. Preserve that outlier. Later comparisons isolate
each variant's source tree and verify every Cargo rebuild set explicitly.
Maximum measured I/O pressure is 2.2%, and CPU pressure is 28.1%.

The shared profile records 520 ms in the compiler worker, close to Cargo's
517 ms median. Its helper has 93 ms of own work; the helper's full workload
contains the compiler and must not be added again. The native-check critical
path includes 117 ms in nested query handling, 117 ms in the Rust function
itself and 112 ms copying compiler state across three directory operations.
These are one capture's exclusive contributions, not a decomposition of
the benchmark median.

The leaf profile records 104 Directory.directory calls to project packages
before hashing them. Their summed duration is concurrent work, not removable
wall time. This motivates a direct subpath hashing experiment.

## Direct package hashing

The isolated helper enables the existing experimental Directory.digest(path)
capability, avoiding the directory projections. It requires the custom engine
API and is absent from the normal Rust module branch. A cache produced by the
original implementation gives 100/102 hits after a leaf edit in this variant;
reverting the edit gives 102/102 hits. This verifies cache identity across the
two hashing paths for this fixture.

The first comparisons share one source tree. Switching variants changes the
shared library's timestamp, so Cargo rebuilds extra crates in leaf trials.
Separate target directories alone do not fix this. Those timing series are
retained but cannot establish a speedup.

The corrected comparison uses independent source trees, Cargo targets and
native histories. Each variant gets four preparation rounds, an invalid-type
tripwire and unique edit values. Five pairs alternate variant order and
Cargo/module order. Every one of the 20 timed Cargo commands has the expected
rebuild set, and native cache counts match all 20 edits.

| Edit | Original module | Direct hashing | Cargo, original / direct |
| --- | ---: | ---: | ---: |
| Leaf | 1,006 ms | 1,034 ms | 87 / 87 ms |
| Shared | 1,578 ms | 1,454 ms | 472 / 488 ms |

Four of five shared pairs improve by 101–130 ms; the other slows by 26 ms.
Four of five leaf pairs are slower. Ranges overlap and maximum CPU/I/O
pressure is 30.3%/13.4%, so the experiment does not establish a general
performance improvement. Keep it isolated rather than selecting it for
ordinary edited builds. Profiles consistently remove 104 projection calls
down to two, with no dropped events.

After direct hashing, one shared profile still attributes 102 ms to three
compiler-state copies, 140 ms to nested query handling and 99 ms to the
Rust module's own work. Avoiding those copies by mounting native state
directly is the next experiment. It must preserve exact result lookup,
incremental seed compatibility, failure behavior and transfer to a fresh
engine. Automatic plan/cache discovery and normal check UX remain unfinished.

Branches:

- [Integration driver](https://github.com/grouville/dagger-rust/tree/experiment/native-module-scalability).
- [Direct hashing experiment](https://github.com/grouville/dagger-rust/tree/experiment/native-module-direct-digests).

Artifacts under /tmp/rust-cache-sipsma-review:

- module-native-102: baseline, failure test and leaf/shared wcprof captures.
- module-native-102-direct-isolated: valid paired comparison and profiles.
- module-native-direct-digests-102-{baseline,equivalence,revert}.log: identity checks.
- measure_native_102.py and measure_native_102_direct_isolated.py: local harnesses.

The flawed source-switching series remain in module-native-102-direct-comparison
and module-native-102-direct-paired. Do not use their timings as evidence of
a performance win.

The [incremental-mount experiment](NATIVE_INCREMENTAL_MOUNTS.md) removes much
of the state-copy cost and passes native transfer, but extra snapshot-reference
queries offset the benefit. It remains isolated while query overhead and the
normal automatic cache workflow are developed.
