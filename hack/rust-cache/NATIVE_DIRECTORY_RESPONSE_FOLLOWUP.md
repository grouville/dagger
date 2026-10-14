# Directory preparation and primitive responses

The additional profiles rule out content-hash lock contention as a useful Rust
optimization in these fixtures. The earlier 138 ms directory-selection cost
does not repeat. Reading a parent frame without cloning it is valid, but the
actual clones total only about 0.25 ms across 104–105 selections. That experiment
is shelved rather than treated as a build speedup.

The primitive-array response experiment helps the many-crate checks, but a small
test-command slowdown persists after swapping the binaries between engines.
Keep it isolated; no production behavior or dependency has changed.

## Identify the directory work

Temporary wcprof phases split directory resolution, lazy evaluation, stat,
snapshot reopening, checksumming and content-digest publication. The active
`engine/contenthash` package also records context lookup and read/write lock
waits. No locks or hash algorithms change.

Nine captures cover three unique edits each through ordinary tests, leaf checks
and shared-library checks. All commands pass, with no dropped events or open
operations. The 102-action cases record four checksum scans, with their combined
durations around 8–12 ms. Hash-context lock waits are mostly microseconds.
Concurrent phase totals must not be read as elapsed time.

A further six captures measure `parent.ResultCall()` directly. Cloning totals
0.234/0.251 ms for the two leaf captures and 0.861/0.246 ms for the two shared
captures; each has 104–105 selections. The two test captures total 0.010/0.011 ms.
Sipsma's [frame-facts change #14627](https://github.com/dagger/dagger/pull/14627)
provides a direct reader, and its existing equivalence regression passes with
race detection. Applying it at the directory readers offers too little measured
Rust benefit to justify a complete-command comparison here. The separate
two-file prototype remains uncommitted and unselected.

Artifacts: `/tmp/rust-cache-sipsma-review/directory-hash-phase-profile` and
`directory-frame-phase-profile`. The large earlier outlier has no established
cause; these captures are not evidence that a hash bug was fixed.

## Retest primitive arrays on the current engine

The [earlier array experiment](NATIVE_SCALAR_ARRAYS.md) bypasses item-result
creation when serializing already computed arrays of strings, integers, floats
or booleans. Explicit item selection, object arrays and wrapped arrays keep
their existing path. The parent result remains cached and persistable.

The port uses engine base `1770e627a` and the same bounded parser and runtime
instrumentation on both engines. It also avoids allocating a fallback response
array before taking the fast path. A new regression adds an unbound resource
dependency during copying and checks that the final response is discarded.
Focused race checks pass for this case, JSON output, explicit item identity,
cancellation, session release, attachment lineage and restored scalar/nested
lists.

Twelve rounds rotate control, candidate and Cargo. Each command sees a fresh
edit in an independent source tree. Cargo targets and project histories are
separate, wcprof is off during timing and telemetry remains enabled.

| Edited command, median | Control | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 0.941 s | 0.968 s | 0.346 s | 4/12 pairs |
| Leaf edit, 102 actions | 0.762 s | 0.712 s | 0.087 s | 9/12 pairs |
| Shared edit, 102 actions | 1.293 s | 1.247 s | 0.492 s | 11/12 pairs |

All 72 native cache probes pass and Cargo checks the expected crates. Maximum
measured CPU/I/O stalls are 27.0%/11.5%. Six complete captures show 410 source-path
item calls disappear from each many-crate command; fourteen disappear from the
test fixture. Total recorded operations fall 7,844→5,384 for leaf edits,
7,718→5,258 for shared edits and 4,599→4,515 for tests. These counts include
internal operations as well as calls, and are not latency estimates.

## Test-command crossover

Swap the control and candidate binaries between the same two engines, keeping
their existing native caches and source trees. After three preparation edits,
repeat twelve rotated test-command rounds with Cargo and 24 native cache probes.

The control median is 0.936 s, candidate 0.950 s and Cargo 0.348 s. The candidate
is faster in 4/12 pairs. The median paired difference is a 7.3 ms slowdown;
subtracting column medians gives 13.6 ms. CPU/I/O stalls peak at 4.0%/7.1%.
Every command and cache probe passes.

Separately, the candidate rejects invalid Rust and changed runtime data, then
recovers 5/5 compiler hits and passes normal tests after restoration. A clean
restart also recovers 5/5; a subsequent application edit reuses 2/5 and passes
normal tests. Those checks are under
`/tmp/rust-cache-sipsma-review/scalar-array-native-correctness`.

The direction of the small slowdown follows the binary after the swap. This
does not explain its cause or prove the same effect for other test suites, but
it is enough to withhold default adoption. A smaller graph alone is insufficient.
The next investigation should measure response costs across list sizes and
inspect the test path before choosing a threshold or adding policy.

Timing and profile artifacts are under
`/tmp/rust-cache-sipsma-review/module-scalar-array-bounded-parser-paired` and
`scalar-array-test-crossover`. No upstream PR has been opened. The full native
Rust cache goal remains open, including Cargo-plus-0.5-second edited commands
and support for registry dependencies, build scripts and procedural macros.

The isolated engine branch is
[`experiment/rust-scalar-array-bounded-parser`](https://github.com/grouville/dagger/tree/experiment/rust-scalar-array-bounded-parser).
It contains only response handling and focused regressions. The bounded parser
and runtime profiling used in these measurements come from the same local
library replacement and overlay as the control, not from a dependency update
in that branch.
