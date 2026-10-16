# Parallel fingerprint scan: not selected

See [the report](../../NATIVE_PARALLEL_FINGERPRINT.md). The component improvement does not establish a consistent full-command gain; serial scanning remains selected. No PR is opened and the upstream proposal count remains eight.

`runs` contains before/after source, exact-byte reference tests, race logs, six fresh-process component pairs, an eight-pair/four-workload full-command series, a listing-only confirmation and six separate profile captures. Every timed command edits a used Rust value. Orders are balanced and randomized per workload; all admitted observations and source values are retained. Instrumented timings are not part of the cohorts. The confirmation reverses the initial favorable listing conclusion.

`engine` records the actual binary hash, build, mode switch and all replacement source hashes. Sources are mirrored under `engine/source-mirror`; the JSON map records each uncompressed source hash. The serial implementation is unchanged apart from its diagnostic name. Parallel mode is off by default and remains off in the final state. Binaries, volumes, targets and Git metadata are excluded.

`retained-cache` verifies six histories after the preserved-volume restart. It prepares any last edit not compiled by Dagger, then requires complete reuse. These unchanged checks are correctness evidence only. Fixture source topology is in the preceding [dimension-key archive](../artifact-dimension-key-fields/); selected configurations are in [native-discovery-selected](../native-discovery-selected/runs/selection.json). Update absolute paths when rerunning. The module is da1ae47b6c96a3117de303b7584d028e35166530 with Rust 1.77.2.

The final runtime state and the rejection decision are in `runs/final-runtime-state.json` and `runs/status.json`. The broader native Rust-cache goal remains active and incomplete.
