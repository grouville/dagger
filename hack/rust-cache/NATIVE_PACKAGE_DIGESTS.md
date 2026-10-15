# Hash native package subpaths directly

The Rust compiler submodule normally selects a `Directory` for every package
before asking for its digest. The existing experimental `Directory.digest(path:)`
API can hash the same subpath without creating that intermediate result. A
one-line module variant enables it on top of the shared dependency index.
Nested packages retain the existing exclusion path. This requires the custom
engine API and remains separate from the module's default behavior.

Implementation: [58ea94a](https://github.com/grouville/dagger-rust/commit/58ea94a).

## Complete edited commands

Both variants use the same warm engine with primitive-array response handling,
Rust 1.77.2 and eight compiler workers. Each has its own source tree and native
history. Every variant receives a distinct fresh edit to prevent cross-variant
compiler-result reuse. Invocation order rotates with native Cargo. Telemetry
stays enabled, wcprof is off, and process exit uses blocking `waitpid`.

| Scenario | Control median | Direct digest median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,026 crates, leaf | 3.019 s | 2.685 s | 0.760 s | 367 ms | 7/8 |
| Leaf, implementations swapped | 2.888 s | 2.573 s | 0.752 s | 346 ms | 8/8 |
| 1,026 crates, shared | 8.844 s | 8.752 s | 5.799 s | −271 ms | 3/8 |
| Small package test collection | 1.091 s | 1.154 s | 0.485 s | −153 ms | 3/8 |
| Small collection, implementations swapped | 0.983 s | 1.019 s | 0.471 s | −30 ms | 1/8 |

The large leaf benefit survives swapping implementations between the existing
histories. Host CPU/I/O stalls reach 14.0%/4.3% in that crossover. The initial
series reaches 27.4%/49.4%, including two candidate shared commands above
20 seconds. All samples remain in the data. Shared compilations establish no
general gain, and the small collection's slowdown reproduces. The variant
therefore stays isolated; these measurements do not select an automatic
size threshold or a global default.

The final large leaf median still exceeds Cargo's median by about 1.82 seconds.
These savings are measured on an engine that already includes primitive-array
responses; their medians must not be added to the earlier array experiment.

## Locate the work removed

Four complete large captures have no dropped events or open operations. Direct
hashing removes 1,026 directory-projection calls in each. In the leaf captures,
total operations fall from 17,373 to 10,191 and the package-hash request falls
from 659 ms to 272 ms. Shared captures show 852 ms to 406 ms for that request.
The encompassing Go submodule's workload includes the compilation program;
those times must not be added together.

Four small collection captures also preserve the expected four executions:
Cargo metadata, Go submodule, compilation program and tests. The package-hash
request falls from 1.5–1.7 ms to about 0.63 ms. That local saving does not
explain the command-level slowdown. Compilation and test intervals also vary;
the remaining difference is not attributed from these four captures.

## Preserve compiler reuse

Switching the hashing path against the previous large cache reuses all
1,026 results and preserves its two-action leaf batch. Both small crossover
variants subsequently reuse all six results; their preceding application
edits each have four execution markers. Thus the small regression is not
caused by compiling extra actions.
Both large crossover variants also reuse all 1,026 results after a leaf edit,
with exactly two execution markers in their current batches.

The variant changes neither the compiler binary nor compilation arguments,
dependency views, incremental-state compatibility or snapshot policy. All
timed commands pass, and every timed large Cargo command has the expected
two or 1,026 rebuilt crates.

[All samples, pressure and profile summaries](experiments/native-package-digests/measurements.json)
are retained. The [workspace generator](experiments/native-worker-index/fixture.py)
produces the large fixture. Local artifacts under the review directory are
`native-direct-digests-index-1026-paired`, `-small-crossover`, `-leaf-crossover`,
`-1026-profile`, `-small-profile` and `-correctness`.
