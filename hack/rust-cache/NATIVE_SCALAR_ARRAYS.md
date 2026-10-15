# Serialize materialized primitive arrays without item cache entries

An isolated engine experiment serializes already materialized arrays of strings,
integers, floats and booleans directly into the existing JSON response shape.
It avoids creating an attached cache result for every array item. Explicit Nth
selection still uses the existing cache path. Wrapped, nullable, nested and
object arrays retain their existing handling.

The response copy holds a session operation, checks the parent result's required
resources before copying, and checks for requirement changes and session release
before returning. Cancellation is checked while copying. The initial resource
test caught misuse of the generation recheck without a full access precheck;
the final implementation includes both checks.

## Verification

Focused race tests pass for primitive JSON output, empty arrays, stable explicit
item identities, unbound and released sessions, cancellation, and release at
operation exit. Existing concurrent Nth selection and persisted scalar/nested
list tests also pass.

The actual Rust module passes cold/edit/revert, configuration recapture, new
target discovery, unsupported build-script rejection and invalid configuration.
Native cache and plan produced by the experimental engine transfer to the
independent control engine, reusing 4/4 actions and then 3/4 after an edit.

Both ordinary-check variants reject invalid Rust and recover their previous
usable cache. All 20 timed Cargo logs rebuild the expected two or 102 crates.
Fresh untimed API probes recover each ordinary command's output with 102/102
reuse, without metadata files.

## Work removed

Two shared-edit wcprof captures have zero dropped events and no open operations.
The source-path response's 410 `String.glob` item calls disappear. Total recorded
operations fall from 7,368 to 4,908, and waits from 834 to 424. Both commands make
100 nested requests; this experiment changes their response handling.

The control's item-call durations total 36.1 ms in this capture. This is work
removed from one profile, not a complete-command speedup estimate. The retained
array remains available for explicit item selection and normal persistence.

## Timing remains inconclusive

Five alternating pairs use fresh control and experimental engines, the same
Rust module code, separate source trees, Cargo targets, project keys and native
histories. Unique edits prevent cross-variant result reuse. Images and compiler
state are prepared before timing; telemetry stays enabled to the local receiver
and wcprof is off.

| 102-action workspace median | Control | Primitive array response |
| --- | ---: | ---: |
| Leaf edit | 0.967 s | 0.882 s |
| Leaf Cargo control | 0.117 s | 0.086 s |
| Shared edit | 1.497 s | 1.812 s |
| Shared Cargo control | 0.935 s | 0.471 s |

Only three leaf and two shared pairs improve. Maximum CPU/I/O pressure is
24.9%/61.3%, and one Cargo command takes 4.8 seconds. The subsequent profiles
also contain large workload delays. These results cannot establish a latency
improvement or regression attributable to the patch. Keep the experiment
isolated pending a less contended confirmation and further review.

Branch: [experiment/materialized-scalar-array-response](https://github.com/grouville/dagger/tree/experiment/materialized-scalar-array-response).
Local artifacts under `/tmp/rust-cache-sipsma-review`: `module-scalar-array-102`,
`scalar-array-transfer-*` and `measure_scalar_array_pairs.py`.

The full Rust cache goal remains open, including persistence and remote
discovery of previous state, retention policy and costs, real toolchain coverage,
and edited complete commands within Cargo +0.5 seconds.

## Retest on the current engine at 1,026 crates

The current variant runs on the selected engine stack, including shared module
schemas and lazy schema hashing. A rebuilt control binary is byte-for-byte
identical to the original. Dependency versions, build settings and container
resource settings match; only primitive-array response handling differs.
The Rust module includes the shared dependency index (`b4b8ffd`) in both arms.

Two existing warm engines have independent histories, and their binaries are
then swapped while preserving their volumes.
Every timed command follows a new source edit. Telemetry remains enabled;
wcprof is disabled during timing. No unrelated build or test runs alongside
the measurements.

### Complete command confirmation

The final eight-pair series uses blocking `waitpid` to measure process exit.
Two earlier series accidentally used Python's timeout polling, which can add
up to 50 ms per command. Those samples remain in the data, but do not establish
small command differences. The original dependency-index experiment did not
use that timer. All figures in this table use the corrected confirmation:

| Edited command | Control median | Primitive response median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,026 crates, leaf | 3.774 s | 3.125 s | 0.815 s | 702 ms | 8/8 |
| 1,026 crates, shared library | 10.094 s | 9.398 s | 5.784 s | 788 ms | 6/8 |
| Small actual package test collection | 1.339 s | 1.332 s | 0.489 s | −19 ms | 4/8 |

The leaf benefit also appears before the binary swap: 328 ms median paired
saving, seven of eight faster. The first shared-edit series is slower overall,
with four wins in eight. Its crossover has six wins and 295 ms median paired
saving. Keep these mixed shared results; the final table alone does not
establish a repeatable general improvement in shared compilations.

Maximum host CPU/I/O stalls in the corrected series are 27.7%/36.9%. Large
outliers affect both engines, including a 20.348 s control leaf command and
a 16.587 s candidate shared command. The small collection establishes no
command benefit. The large leaf reduction is the strongest complete-command
evidence; the Cargo +0.5 s target remains unmet.

### Work removed and work still expensive

Four complete captures have no dropped events or open operations. The source
path response's 4,106 `String.glob` item calls disappear. Shared-capture
operation count falls from 41,931 to 17,215; leaf count falls from 42,009 to
17,293. The underlying directory enumeration takes 18–22 ms in both arms.
The containing request falls from 362–464 ms to 41–43 ms. This locates the
change in response handling after enumeration. These are profile wall times,
not additional savings to add to the command measurements.

The captures also expose much larger intermittent costs. One candidate leaf
command spends 27.582 s in `withExec.applyOutputs`, after its compiler program
finishes. A control shared command spends 5.819 s copying a directory. A
36.805 s control shared command occurs after the binary swap. These pauses
occur in both implementations; they cannot be assigned to primitive-array
serialization from elapsed time alone. The next diagnostic splits output
application into snapshot-manager lock waits, backend commit, metadata and
binding. It preserves the locks and snapshot behavior.

Four subsequent diagnostic captures do not reproduce that pause. Output
application takes 5.2–5.3 ms for leaf compilation and 97–98 ms for shared
compilation. The latter is mostly backend commit of `/rcexp-results`
(91–97 ms). Snapshot-manager lock waits total at most 0.295 ms per capture.
These observations do not justify a locking change. The scoped
[diagnostic patch](experiments/native-scalar-array-scale/output-commit-diagnostic.patch)
remains available for a future slow capture; it changes no snapshot or retention
policy.

Five-second engine CPU windows still contain substantial span export and
protobuf JSON conversion. They cover different phases and concurrent engine
work, so neither their CPU totals nor their call trees are a normalized
complete-command comparison. Telemetry remains enabled.

### Check the real commands

Post-timing probes recover 1,026/1,026 large results and 6/6 small results on
both engines. Current snapshots contain 1,026 execution markers for the last
shared edit and four for the small collection's application edit. A fresh large
leaf edit on the candidate compiles exactly two actions and then reuses all
1,026 results. The collection rejects invalid Rust, a changed file read at test runtime, and a
failing doctest. Restoring input recovers all six compiler results and passes
the actual tests. A fully reused historical result need not have a current
execution batch; the restoration probe checks reuse rather than requiring one.

Focused race tests on the exact engine overlay cover primitive responses,
explicit item identities, session/resource checks, concurrent Nth access and
persisted scalar/nested lists. The experiment stays isolated while snapshot
costs and integration are investigated; no upstream PR is opened.

Implementation: [d6595788e](https://github.com/grouville/dagger/commit/d6595788e).
The [workspace generator](experiments/native-worker-index/fixture.py) and
[all measurements](experiments/native-scalar-array-scale/measurements.json)
preserve the inputs and results. Local artifacts are `native-scalar-array-1026-`
`{paired,crossover,precise,profile,correctness}` under the review directory.
