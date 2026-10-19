# perf(dagql): build argument definitions without copying input specs

Schema construction copies selected `InputSpec` values into a temporary slice, then reads that slice to build argument definitions. Repeated schema preparation during Go collection expansion makes these short-lived copies expensive.

Share the selection algorithm as indices into the original specs. `ArgumentDefinitions` builds its output directly; Inputs still returns a separate list. This is part of reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Measurement | Before | After |
| --- | ---: | ---: |
| Complete listing after a test edit | 6.76 s | 6.58 s |
| Cumulative engine allocation | 6.313 GB | 6.114 GB |
| Eight argument definitions | 3.45 µs / 4,012 B | 2.94 µs / 2,731 B |

Four alternating pairs per comparison. Complete listing improves **2.7%**, faster with lower CPU and allocation in every pair. Paired elapsed savings range from 6 to 414 ms, with a 157 ms median.

Commands start a fresh CLI on the same warm experimental engine, make real edits, and include telemetry and successful cleanup. All 800 getters, 804 module evaluations and 799 discovery hits remain. Source-edit CPU and allocation are effectively flat.

### Validation and tradeoffs

Both standalone and development-engine full DagQL race suites pass. Tests cover visibility, override precedence, metadata and output ownership. The 27 Go checks, 28 Rust/native-cache cases and all 24 timed commands have their expected outcomes.

Direct Inputs callers above 15 raw arguments incur one extra temporary allocation. The 16-argument control moves **1.712 → 1.767 µs**, adding 128 bytes. The patch adds no cache or lock and retains argument order, defaults and validation.

[Source](https://github.com/grouville/dagger/tree/experiment/schema-argument-iteration). [Measurements and reproduction](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_SCHEMA_ARGUMENT_ITERATION.md).
