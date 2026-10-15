# Content-keyed syntax construction

Apply `content-key.patch` after the bounded parser-cache prototype and phase hook
described in [the previous experiment](../dang-parse-blueprint-bounded/README.md).
It changes only `pkg/dang`'s experimental cache and its tests. The syntax cache
remains local acceleration; compiler results still use native Dagger snapshots.

```sh
git apply /path/to/content-key.patch
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -race -count=1 ./pkg/dang ./pkg/hm
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -run '^$' -bench '^BenchmarkRustModuleBlueprint(MountPaths)?$' \
  -benchmem -benchtime=500ms -count=3 ./pkg/dang
```

`component.json` retains all component samples, including the superseded variant
that boxed the current filename once per source location. `commands.json`
contains both eight-pair command series and all pressure measurements.
`mounts.json` records the actual mount paths and phase times before and after
idle expiry. `measure.py` and `profile_mounts.py` preserve the local drivers.

The command driver expects the prepared experimental modules and engines at its
explicit `/tmp` paths. Initial assignment: filename-key engine on 16276 and
content-key engine on 16275. The `--crossover` run expects the binaries swapped
on those same engines, preserving both volumes, and uses four preparation
rounds. It measures fresh edits through actual workspace checks and the Rust
package test collection, with native Cargo controls and telemetry enabled.

The [report](../../NATIVE_PARSE_CACHE_CONTENT.md) distinguishes the demonstrated
remount reuse from the inconclusive full-command latency results. This remains
an isolated experiment, with no upstream PR or dependency change.
