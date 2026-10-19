# perf(go): avoid reconstructing every module owner for each package

Resolving a package currently reconstructs every module owner held by its collection, including the settings repeated in each owner. On dagger/dagger that happens for 800 packages and 80 modules after a test-file edit.

Keep the shared tool settings once and index the small ownership facts by module path. The existing package getter finds the deepest owning path and constructs only its selected module through `goModuleAt`. Authored getters, per-key cache lookup, source snapshots and test selection keep their normal execution paths. An explicit constructor keeps the index private.

Complete `dagger check --module go --check test --list --all` on the real repository:

| Edit | Before | After |
| --- | ---: | ---: |
| Test file | 11.47 s | 9.56 s |
| Ordinary source | 6.54 s | 6.21 s |

Each row is the median of four balanced pairs on a warm engine, with a fresh CLI and real edits. Both arms finish test addition and removal before measured pairs. Every pair improves. All 24 commands return the correct ordered rows and exit successfully, including telemetry, final flushing and session cleanup. Profiling is separate from timing.

For test edits, median engine CPU falls 60.71 → 49.60 CPU-s and allocation 13.68 → 11.08 GB. Lossless profiles retain all 800 getters and the same 799 test-discovery hits plus one execution. Getter receiver data falls 81.4 → 52.1 MB and reconstructed lists 392,000 → 6,400. The SDK request count is unchanged.

Nine focused checks pass, including nested ownership, exclusions, source overrides, module-boundary edits and real test/build/generate execution. The new settings check covers a custom base, flags, extra input files and mount path; rebuilding an owner with default settings makes that check fail. No engine or dependency change is involved.

These measurements use the existing experimental engine and native-source/getter-identity module stack, with schema reuse enabled equally in both arms. This branch is based on `a3d0e4bf562b834c31135bff24e5931fd32b3acc`; a port and repeat benchmark on upstream module main remain necessary. Cold and Rust performance effects are unmeasured. Exact timed and final sources, all attempts and complete profiles are preserved in the experiment evidence.
