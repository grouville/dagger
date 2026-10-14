# Avoid reconstructing unused check results

The isolated Rust module branch shares native compilation and cache publication
through a private function returning the compiler helper's object directly.
The ordinary `check` waits for its artifacts without reconstructing the public
`NativeCompilation` and its cache fields. The public `nativeCheck` API still
returns artifacts, cache, plan and counters in the existing form.

The normal path removes work, but this experiment does not establish a general
command speedup. Keep it isolated rather than select it as the default backend.

## Measurements

Five alternating pairs per scenario use complete ordinary `dagger check`
commands on the same engine. Each variant has separate source trees, Cargo
targets, project keys and native histories. Unique host edits prevent shared
compiler-result hits between variants. Three preparation rounds precede timing.
Telemetry stays enabled to the local receiver; wcprof is off during timing.

| 102-action workspace median | Original check | Direct helper result |
| --- | ---: | ---: |
| Leaf edit | 0.882 s | 0.909 s |
| Leaf Cargo control | 0.088 s | 0.091 s |
| Shared edit | 1.419 s | 1.374 s |
| Shared Cargo control | 0.473 s | 0.479 s |

Only three of five pairs improve in each scenario. Maximum CPU/I/O pressure is
27.2%/37.6%, limiting the timing conclusion. All 20 Cargo logs rebuild the
expected two or 102 crates. Untimed fresh API probes recover every ordinary
check's output with 102/102 hits; neither variant uses a metadata directory.

Both shared-edit profiles have zero dropped events and no open operations.
Nested requests fall from 100 to 92, and `Query.node` calls from 83 to 67.
Check execution outside recorded nested work falls from 131.6 to 106.8 ms in
these two captures. Other preparation work varies enough to leave the complete
profile slightly slower, 1.28 versus 1.33 seconds. These are phase observations,
not independent savings that can be added together.

## Correctness and next target

Actual-module source edits reuse 3/4 actions. Invalid Rust fails, followed by a
valid 3/4 edit. Configuration changes refresh the plan, ordinary checks publish
recoverable state, and explicit transfer reuses 4/4 actions on a separate engine
then 3/4 after a source edit. The writer's new-target, unsupported build-script
and invalid-configuration checks pass. Compiler and engine code are unchanged.

The profiles also identify 410 `String.glob` calls. These are scalar list-item
cache operations created while serializing the source-path list, not 410
filesystem glob walks. `Directory.glob` itself takes about 3 ms. In the candidate
capture, the item calls and their publication total about 28 ms.

The relevant path is `dagql.Server.resolvePath`: even a plain scalar array with
no subselections calls `loadNthValue` for each item. `Result.NthValue` publishes
an attached cache entry for each. A narrowly scoped serialization path for
already materialized primitive arrays is a concrete next engine experiment.
It must preserve output, session and resource checks, while leaving explicit
Nth selections and object/list lifecycle behavior intact. No engine change for
this is included here.

Branch: [experiment/native-check-minimal-result](https://github.com/grouville/dagger-rust/tree/experiment/native-check-minimal-result).
Artifacts under `/tmp/rust-cache-sipsma-review`: `module-minimal-check`,
`module-minimal-check-102`, `minimal-check-transfer-*`, `verify_minimal_check.py`
and `measure_minimal_check_pairs.py`.

Persistent and remote cache discovery, physical retention, real toolchain
coverage and the full Cargo +0.5-second target remain unfinished.
