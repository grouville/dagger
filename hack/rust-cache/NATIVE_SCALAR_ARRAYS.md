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
