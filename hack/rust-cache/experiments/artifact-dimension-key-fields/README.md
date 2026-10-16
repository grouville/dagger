# Direct artifact dimension-key reads

Standalone patch: grouville/dagger 104f7ab5b211a739b29cce40bd0fe492617b1b86, directly on upstream main 717589c9ccacbba7d3cf902647aa5c9ca68085e8. No PR is open.

See [the report](../../NATIVE_DIMENSION_KEY_FIELDS.md) for complete results and limits.

`runs/commands-stable` and `runs/confirmation` contain two eight-pair complete-command cohorts. The confirmation reverses Dagger ordering. Warmup rounds are explicitly marked. `runs/check-only-control` isolates compilation; `runs/identical-policy-control` keeps both labeled arms on the original code. All observations, pressure and Go-GC counts are retained. `runs/main-validation` contains six fresh-process component pairs, exact binary hashes, before/after compatibility logs and the standalone race log.

`runs/profiles` contains separate CPU/runtime/wcprof diagnostics. `lock-discovery` retains earlier engine runtime traces with wcprof enabled and disabled. Instrumented timings are not benchmark observations; concurrent wait and CPU totals are not additive wall time.

`engine` records the exact build, controlled policy callback, original baseline overlays and hashes. Every replacement source is mirrored under `engine/source-mirror`; its map records the uncompressed source hash. The production patch only adds two struct tags. The dynamic callback, atomic flag and HTTP handler are diagnostics. Test binaries and the engine binary are excluded.

`retained-cache` verifies six native Rust histories after the preserved-volume restart. The helper prepares the current source, then demands complete reuse. The fixture archive contains final Cargo sources and configuration, excluding targets and Git data. Drivers generate fresh random source edits. Original measurements require the native Rust module 3cd40e5928563ade3ea1cd21ab9924cd03d88fc3, Rust 1.77.2 and the recorded CLI/engine overlay setup; update absolute paths when rebuilding. Initialize a local Git boundary in each fixture so default-path resolution has the same scope.

Initial harness failures remain under `initial-harness`. They include outdated test API calls, typed-response assertions and a source overlay that initially omitted existing experimental helpers. The final baseline preserves those helpers and changes only the two getter policies.

Direct getter reads are enabled for subsequent work on the owned engine; final idle state is recorded in `runs/final-runtime-state.json`. Profiling and other temporary modes are off, and ordinary snapshot collection remains enabled. This experiment does not complete the native Rust-cache roadmap.
