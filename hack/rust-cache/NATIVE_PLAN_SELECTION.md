# Select compiler plans through the native Rust cache

The isolated Rust module branch retains the compiler plan as a native File in
`NativeCache.plan`. `nativeCheck` can now capture its first plan without a
separate capture call. Later calls use the previous cache's plan. An explicit
`compilerPlan` still takes precedence and keeps strict validation.

Automatic selection compares the pinned image, Cargo command and flags,
configuration-directory digest, and sorted source paths. Ordinary content
edits reuse the plan; configuration or path changes recapture it. Tracking all
paths is conservative: adding a documentation file can also recapture. It
prevents newly discovered Cargo targets or build scripts from silently using
an obsolete graph. Validation metadata stays outside compiler/seed identities;
the actual graph, configuration, sources and dependencies determine reuse.

`nativeCache = true` selects this backend for the normal `check` entrypoint.
One actual workspace runs `dagger check rust:check` successfully with that
setting, a pinned image and `locked = true`, without an explicit plan. Cold
setup took 10.3 seconds; that includes capture and compilation.

This does not finish automatic cache discovery. The engine currently exposes
no native latest-result lookup for the module. Callers still retain and supply
the previous `NativeCache`, or configure `compilerCache`. Ordinary check calls
without a previous cache do not automatically recover rustc incremental state.
The default Cargo path and the experimental path-only boundary remain.

## Verification

- Focused model, replay, worker and wrapper tests pass.
- Explicit-plan cold/edit/revert/configuration-rejection checks still pass.
- Automatic cold compilation, configured normal check, 3/4 edited reuse and
  4/4 reversion pass. The plan bytes remain identical across ordinary edits.
- A manifest edit recaptures successfully; adding a binary target changes the
  captured graph from four actions to five.
- Adding a build script recaptures and rejects the unsupported package.
  Invalid Cargo configuration also fails.
- Transferred cache and plan reuse 4/4 actions on a separate engine, then 3/4
  after another edit.
- Invalid Rust in the 102-action fixture fails without updating cache metadata.

The generated Go dispatcher and dependency bindings are regenerated through
`ModuleSource.generatedContextDirectory`. The extra plan field is optional in
the local cache and transfer helper; legacy caches can trigger a fresh capture.

## Fresh edited commands

Five samples per scenario use actual host edits, fresh command sessions, three
shared/leaf preparation rounds and an independent Cargo target. The driver
retains the cache and plan handles on the engine rather than uploading plan
JSON on every edit. It reads plan bytes again only when the returned handle
changes. Local handles remain an acceleration mechanism for that engine;
transfer carries the plan and native directory data.

| Complete-command median | Native module | Cargo |
| --- | ---: | ---: |
| Leaf edit | 0.939 s | 0.086 s |
| Shared edit | 1.431 s | 0.515 s |

Every native count matches 100/102 or 0/102 hits. All ten Cargo rebuild sets
match two or 102 crates. Telemetry stays enabled to the local receiver; wcprof
is off during timing. Maximum CPU/I/O pressure is 25.9%/2.1%. Both subsequent
captures have zero dropped events. This series measures the new workflow;
it is not a matched before/after speedup claim and does not meet Cargo +0.5 s.

Remaining work: automatic previous-cache indexing, coverage for real registry
dependencies, build scripts, procedural macros and tests, physical retention
and transfer costs, and lower module/preparation overhead.

Branch: [experiment/native-plan-selection](https://github.com/grouville/dagger-rust/tree/experiment/native-plan-selection).
Artifacts under `/tmp/rust-cache-sipsma-review`: `auto-plan-*`,
`module-auto-plan-102`, and `measure_auto_plan_102.py`.
