# Native compiler helper inputs and binary tests

Combining compiler input reads removes three Dagger requests per edited command,
but does not establish a latency improvement. The change stays isolated. The
correctness checks also found a separate Cargo test bug: normal and test builds
of the same binary were both considered as the final executable. A small fix
now makes a real integration test using `CARGO_BIN_EXE_added` pass.

## Combine input reads

The helper reads Cargo configuration and source paths to validate its captured
plan. Graph construction then reads the configuration again and requests the
package source hashes. The experiment combines configuration, paths and package
hashes in one aliased request. It passes a private validation token into graph
construction, tied to the immutable source and serialized plan. Changed inputs
cannot substitute hashes. If a removed package makes an old projection fail,
ordinary configuration/path validation preserves the recapture path.

Engine base, bounded parser, telemetry and compiler/cache policies are the same
for both modules. Both use the same engine. Eight rounds rotate control,
candidate and Cargo on independent source trees and Cargo targets. Every timed
command sees a unique edit; wcprof is off during timing. All 48 follow-up native
cache probes pass. Cargo checks the expected two or 102 crates for timed edits.

| Edited command, median | Control | Candidate | Cargo | Candidate faster |
| --- | ---: | ---: | ---: | ---: |
| Tests | 1.017 s | 1.069 s | 0.363 s | 4/8 pairs |
| Leaf, 102 actions | 0.790 s | 0.808 s | 0.088 s | 2/8 pairs |
| Shared, 102 actions | 1.348 s | 1.379 s | 0.515 s | 4/8 pairs |

CPU/I/O stalls reach 36.4%/64.2%; keep all samples and avoid attributing the
differences solely to the change. Median paired savings are -2.0 ms for tests,
-87.4 ms for leaf edits and +8.5 ms for shared edits. This is insufficient
evidence to add the implementation complexity to the preferred module.

Six complete wcprof captures confirm three requests disappear in every case:
103→100 for leaf, 95→92 for shared and 109→106 for tests. One configuration
digest call also disappears. No executions or compiler inputs are removed.
These operation counts establish less protocol work, not a build speedup.

The earlier query-shape diagnostic logged redacted requests from six edited
commands. That logging changes telemetry volume, so its command timings are
excluded. An incorrectly rooted diagnostic fixture initially imported its
artifact parent; it was canceled and replaced with projects rooted separately.

Focused replay/model race checks and static checks pass. A real package move
recaptures the plan, passes normal tests and subsequently recovers 5/5 compiler
hits. Invalid Rust and changed runtime data fail, then restoration recovers
5/5. A clean engine restart also recovers 5/5; a subsequent edit reuses 2/5 and
passes normal tests. These lifecycle checks are under `helper-query-batch-correctness`.
The branch is
[`experiment/native-helper-query-batch`](https://github.com/grouville/dagger-rust/tree/experiment/native-helper-query-batch),
commit `b3aac25`, based on module `7d5c1a4`.

Artifacts are under `/tmp/rust-cache-sipsma-review/helper-query-batch-paired`.
Diagnostic captures are under `helper-query-profile-rooted-captures`; the
package-move checks are under `helper-query-batch-package-invalidation`.

## Select the normal binary for publication

`cargo test` compiles a binary both normally and with `--test`. These invocations
share a package, crate name and source path, but produce different executables.
The publication matcher considered both and rejected Cargo's final binary path
as ambiguous. Cargo's artifact message includes `profile.test`; matching it
against the captured action's `--test` flag selects the correct invocation.

The focused regression fails before the patch and passes after it. Replay,
model, worker, compiler-wrapper and test-recorder checks pass with race
detection. A real Cargo workspace reproduces the failure on the old module and
passes on the fix. Its integration test launches the binary through
`env!("CARGO_BIN_EXE_added")` and checks its output. Changing the binary to print
the wrong value fails that test; restoration and a further source edit pass.
Follow-up probes recover 8/8 compiler results as native Dagger objects.

The fix is isolated on
[`fix/native-cargo-test-binary-publication`](https://github.com/grouville/dagger-rust/tree/fix/native-cargo-test-binary-publication),
commit `f136cb4`, also based on `7d5c1a4`. It changes only publication matching
and its regression. Real fixture checks are under
`/tmp/rust-cache-sipsma-review/test-binary-publication`.

No upstream PR is opened. This resolves one normal Cargo test case; registry
dependencies, build scripts, procedural macros and the complete edited-command
performance target remain unfinished. The helper launch remains in place.
