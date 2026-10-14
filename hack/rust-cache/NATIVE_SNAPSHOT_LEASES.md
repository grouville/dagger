# Trace snapshot ownership waits through the Rust module

The diagnostic engine tags each snapshot-lease mutex with its result ID and
records the time held, ownership reads and individual attach/remove calls.
It preserves the lock and lease operations. The added result formatting only
runs with wcprof enabled. Focused ownership, publication, persistence and
snapshot-sharing tests pass.

Six profiles use fresh host edits through the actual 102-action module on a
separate engine, after cold setup and three warm shared/leaf rounds. Every
capture has zero dropped events and the expected 0/102 or 100/102 reuse.

| Scenario | Longest holds in three captures | Ownership collection | Lease update |
| --- | --- | --- | --- |
| Leaf | 37.5, 38.7, 27.4 ms | 26.6–38.1 ms | 0.5–0.8 ms |
| Shared | 118.8, 125.4, 109.1 ms | 108.3–124.7 ms | 0.7–0.8 ms |

The long holds belong to `Container.withNewFile`, where the ownership reader
waits for `core.lazyGroupOnce.mu`. It waits for lazy container parts to finish
publishing their snapshots before reading a coherent ownership set. The lease
database updates themselves account for less than a millisecond. Moving or
removing the outer mutex would not remove the underlying publication wait.

These waits also overlap required snapshot preparation. One shared critical
path attributes 163.1 ms to artifact/state copying, without counting the
125 ms lease wait as an additional phase. Do not sum those intervals or claim
that removing a mutex would save another 125 ms. A change to ownership reads
would need a repro proving unnecessary serialization and regression coverage
for concurrent publication, cancellation and snapshot retention.

Diagnostic branch: [experiment/rust-cache-lease-profile](https://github.com/grouville/dagger/tree/experiment/rust-cache-lease-profile).
Artifacts: `module-native-lease-profile`, `profile_native_102_leases.py` and
`analyze_lease_holders.py` under `/tmp/rust-cache-sipsma-review`.

## Mount the worker request as a File

A separate one-line module experiment mounts the worker's JSON request as a
native File rather than copying it into the image filesystem. The worker only
reads that file. Its content remains an ordinary execution input; compiler
results and incremental state remain native directories.

Five alternating pairs use independent source trees, Cargo targets and native
histories on the diagnostic engine. Unique edits prevent cross-variant compiler
hits. Four preparation rounds and an invalid shared-library type check precede
timing. Telemetry stays enabled; wcprof is off during timing. Every native hit
count and all 20 Cargo rebuild sets match the expected dependency graph.

| Complete edited-command median | Write into rootfs | Mount File |
| --- | ---: | ---: |
| Leaf | 0.878 s | 0.850 s |
| Leaf Cargo | 0.093 s | 0.087 s |
| Shared | 1.409 s | 1.351 s |
| Shared Cargo | 0.475 s | 0.487 s |

Three of five pairs improve in each scenario. Maximum timed CPU/I/O pressure
is 26.4%/25.9%; ranges overlap, so the 28/59 ms median reductions are tentative.
Both shared profiles still have roughly 115–118 ms lease waits. The mounted
request does not resolve the underlying publication barrier.

Focused backend tests and actual-module cold/check/edit/revert/transfer checks
pass. Keep this small change as an isolated experiment pending stronger timing
evidence. Branch: [experiment/native-mounted-request](https://github.com/grouville/dagger-rust/tree/experiment/native-mounted-request).
Artifacts: `mounted-request-*`, `module-native-102-mounted-request` and
`measure_native_102_mounted_request.py` under `/tmp/rust-cache-sipsma-review`.
