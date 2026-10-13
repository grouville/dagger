# Current SDK comparison

The Rust replay was forward-ported to upstream `f9d7e23a` and its Go SDK API.
The engine connection stays in `dagger.io/dagger`; query objects now come from
`dagger.io/dagger/core`. Builders accept the generated `Query` rather than the
transport client. Compiler actions, source keys and native history selection
are unchanged. Helper binaries disable VCS stamping so they can build from an
isolated worktree and do not vary with unrelated repository commits.

This makes the prototype usable with the current API, including Sipsma's
[#14593](https://github.com/dagger/dagger/pull/14593) ID memoization. The
measurements do not establish a performance improvement for our batched backend,
so the migration stays separate from the existing performance reference.

## Edited builds

Both drivers request the beta.17 schema and use the same local engine, Rust
1.77.2, synthetic 102-action workspace, automatic native history and digest-path
extension. The engine includes the owner index, digest-path experiment and
Sipsma's two telemetry optimizations. It is unchanged between variants. The
legacy control is built with a temporary Go source overlay that changes only
its requested schema version from beta.15 to beta.17.

Five alternating pairs per scenario, four preparation edits per history,
rotating Cargo/replay order, two series. These are new edits with populated
caches and retained incremental state. Command wall time includes export,
history retention and shutdown. Telemetry stays enabled to the approved local
receiver with a dummy token and empty client configuration; production Cloud
latency is unmeasured.

| Series | Edit | Legacy median (range) | Current SDK median (range) | Cargo medians legacy / current |
| --- | --- | --- | --- | --- |
| First | Leaf | 0.593 s (0.557–0.634) | 0.563 s (0.547–0.597) | 0.213 / 0.213 s |
| Repeat | Leaf | 0.570 s (0.558–0.627) | 0.605 s (0.553–0.612) | 0.211 / 0.217 s |
| First | Shared | 1.780 s (1.486–2.196) | 1.899 s (1.536–2.377) | 0.836 / 0.842 s |
| Repeat | Shared | 1.303 s (1.268–1.324) | 1.315 s (1.290–1.414) | 0.675 / 0.641 s |

The initial leaf improvement reverses in the repeat. The first shared series
has substantial host contention, with Cargo slower too; its apparent 119 ms
regression falls to 12 ms in the repeat. Ranges overlap. There is no repeatable
command speedup here, and the data do not rule out a small regression.

Separate wcprof captures of one fresh shared edit per driver record the same
15 query requests, eight `Directory.id` operations and one `File.id` operation,
with 539 recorded operations and zero dropped events on each side. ID memoization
does not reduce requests on this captured path. The new-client capture's output
application takes 185 ms versus 16 ms; that single capture does not attribute
the variation to the SDK.

## Correctness

All 40 timed edited builds pass the harness's checks for compiler invalidation,
exported bytes and modes, new values in the executable, full finished-result
reuse and retained history. No history fallback occurs.

The model, replay, worker and wrapper packages pass their existing tests with
the race detector. The full `TestRustCompilerReplay` integration passes in
70.95 seconds: two fresh nested engines, transferred native artifacts and
incremental state, exact finished-result reuse, and recompilation after a new
edit on the receiver. That test also exercises the digest-path extension. Its
first attempt failed while building a Go helper because VCS metadata was
unavailable; the retry passes after disabling that unnecessary stamping.

Raw evidence is under `/tmp/rust-cache-sipsma-review`: `sdk-{comparison,repeat}`,
`sdk-profile-{legacy,v1}`, `sdk-v1-{tests,race}.log`, and
`sdk-v1-rust-integration{-retry,}.log`. The isolated source checkout is
`/tmp/dagger-rust-sdk-v1`, branch `experiment/rust-native-cache-v1`.
