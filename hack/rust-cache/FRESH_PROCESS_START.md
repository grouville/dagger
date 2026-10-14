# Fresh process startup on warm caches

Fresh processes can start faster, and independent starts already overlap. The
remaining runtime cost is much smaller after Sipsma's
[crun change #14607](https://github.com/dagger/dagger/pull/14607). It merged on
October 14. Our [Rust comparison](NATIVE_PROFILE_FOLLOWUP.md#runtime-comparison-through-the-native-module)
measured two runtime starts falling from 75–103 ms to about 21–22 ms. The latest
[ordinary Rust check profile](NATIVE_CACHE_DISCOVERY.md) records 24.93 ms for
those two starts. These figures cover runtime creation, not all filesystem
preparation or the complete command.

## Isolating the start cost

On October 14, the same warm engine ran `/usr/bin/true` with unique arguments
on every invocation. Each action therefore misses and starts a fresh process.
The image, toolchain and engine caches are warm. Nesting is disabled; telemetry
remains enabled through the local collector.

The study compares one execution, two executions connected by `withExec`, and
two independent executions selected in one query. It prepares all three cases,
then alternates their order over eight rounds. wcprof remains enabled for these
diagnostic samples. Every capture confirms the expected one or two successful
executions, with no dropped events or unfinished operations.

| Median | One process | Two sequential | Two independent |
| --- | ---: | ---: | ---: |
| Execution span | 19.57 ms | 37.57 ms | 19.58 ms |
| Sum of runtime-start phases | 11.26 ms | 19.42 ms | 20.98 ms |
| Complete query command | 330 ms | 332 ms | 323 ms |

Execution span is the interval from the first `exec.run` start to the last
`exec.run` end. It includes setup, the no-op workload and cleanup within those
operations. It excludes earlier snapshot preparation and later output
publication. Concurrent phase totals must not be added to elapsed time.
Sequential spans range from 28.52 to 42.98 ms; independent spans range from
16.34 to 22.03 ms, and all eight paired execution spans improve. Complete query
command ranges overlap and only five pairs improve. Maximum CPU pressure is
3.4%, and I/O pressure is 12.9%. The command samples do not establish a general
latency gain.

An initial eight-round series gave spans of 19.68, 33.72 and 18.52 ms. Its
complete-command measurements used Python's timeout polling and are unsuitable
for comparing small command differences; the table uses a confirmation without
that polling. The execution profiles from both series remain valid.

## Consequence for Rust

Parallel starts roughly halve this simple execution span, but our Go helper
constructs and launches the Rust compiler worker. Those two executions have a
real dependency and cannot be made independent just by scheduling them together.
The worker already batches compiler misses: a 102-crate workspace does not start
102 compiler containers.

Three possible directions remain:

- Reduce runtime/init work while preserving fresh execution. The existing
  [nonblocking session change](NATIVE_PROFILE_FOLLOWUP.md#nonblocking-session-helper-comparison)
  already moves readiness work off process spawn; a helper that immediately
  calls Dagger still waits at its first query.
- Avoid the extra Go helper execution by moving its graph construction into
  the Rust module or another suitable runtime. This could also remove part of
  the helper protocol, but porting the implementation has a maintenance cost
  and its complete-command benefit is unmeasured.
- Reuse a worker or prepared execution environment. This needs per-call
  filesystem state, environment, cancellation, logs and result publication.
  A shared writable `target` directory would lose the native cache design.

Runtime creation alone offers tens of milliseconds in the current Rust path.
It cannot explain the remaining several-hundred-millisecond gap. Snapshot
copies, query handling and module orchestration remain larger measured targets.
This study changes no production executor behavior and establishes no new Rust
build speedup.

## Reproduce

Use an idle, isolated engine with wcprof and a CLI pointed at that same engine.
Keep captures outside the checkout. For the local benchmark wrapper:

```sh
RUST_CACHE_BENCH_RUNNER=tcp://127.0.0.1:16263 \
  python3 hack/rust-cache/exec_start.py \
  --debug-url http://127.0.0.1:16091 \
  --out /tmp/fresh-process-start-new \
  --image rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42 \
  --runs 8 -- python3 /tmp/rust-cache-sipsma-review/local_cli.py
```

The script creates a new capture directory, records each query and profile, and
saves samples and medians. Artifacts for this study are under
`/tmp/rust-cache-sipsma-review/fresh-process-start` and
`/tmp/rust-cache-sipsma-review/fresh-process-start-confirmation`.
