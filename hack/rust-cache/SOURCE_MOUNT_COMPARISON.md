# Read-only compiler source mounts

This experiment mounts compiler source directories read-only in batched and
per-crate replay. Rustc's outputs and incremental state remain writable in their
dedicated output mounts. The worker writes its dependency views, normalized
dep-info and execution markers there, not into source directories.

It applies the same principle as
[#14630](https://github.com/dagger/dagger/pull/14630): an input the command does
not modify need not become another mutable snapshot output. Source digests and
all compilation inputs remain part of the action's cache identity. The engine
already omits output application for read-only mounts.

## Measurements

The two drivers use the same current SDK, beta.17 schema, engine and 102-action
Rust 1.77.2 fixture. They differ only in the source mount option. Each series
has five alternating pairs per edit scenario and four native-history preparation
edits. Telemetry is active to the local dummy-token receiver. Complete command
times include exports, history retention and shutdown.

| Series | Edit | Writable median (range) | Read-only median (range) | Cargo medians writable / read-only |
| --- | --- | --- | --- | --- |
| First | Leaf | 0.630 s (0.569–0.826) | 0.674 s (0.562–0.769) | 0.216 / 0.221 s |
| Repeat | Leaf | 1.315 s (0.582–1.842) | 1.106 s (0.592–1.606) | 0.489 / 0.368 s |
| First | Shared | 1.551 s (1.286–1.957) | 1.784 s (1.255–4.776) | 0.672 / 0.645 s |
| Repeat | Shared | 1.854 s (1.380–2.099) | 1.609 s (1.256–8.222) | 0.887 / 1.088 s |

Both apparent slowdowns reverse in the repeat. The host had large CPU and disk
contention, and Cargo also had multi-second outliers. No samples were removed.
These measurements do not establish a command speedup or rule out a regression.

One fresh shared-edit wcprof capture per variant has output application at
17.94 ms writable and 12.77 ms read-only. Complete profiled commands are 1.837 s
and 1.802 s. This shows where to look, but one pair under host contention is not
enough to attribute the difference to the mount option.

## Correctness and decision

All 40 timed edited builds pass compiler invalidation, exported bytes and modes,
new executable values, complete finished-result reuse and retained-history checks.
No history fallback occurs. The read-only source mount experiment has not run
the transferred-state integration test; that test passed on the SDK migration
before this separate change.

The source mount option remains an experiment and is absent from the existing
performance reference and the pure SDK migration branch. Its two-line patch is
saved at `/tmp/rust-cache-sipsma-review/source-readonly.patch`; the tested binary
is `/tmp/rust-cache-profile-bin/rcexp-source-readonly`. Timing and pressure files
are in `readonly-{comparison,repeat}`, and profiles are in
`readonly-profile-{before,after}` under the same review directory.

The next useful measurement needs a quieter host and should count source
snapshot preparation and commit separately. Fewer writes are worth testing,
but should not be presented as a proven latency improvement.
