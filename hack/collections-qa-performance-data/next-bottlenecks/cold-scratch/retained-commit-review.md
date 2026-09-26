# Cold and persistence changes above main: review

Reviewed September 25, 2026 against main base `d8f1f0d6d2` and branch
`c12a34663b`. These are our performance commits, not the collections feature
commits carried by the same branch. No source was changed for this review.

| Commit/change | Decision | Evidence and follow-up |
| --- | --- | --- |
| `80baa2eb11`, image import wcprof boundaries | Keep as observability | Separates import lock wait, prepare, apply, commit. No identity, ownership, error or GC policy change. `BeginOp`/wait return nil when no recorder exists; nil-safe endings keep normal operation cheap. Sipsma's acquisition #14229 and sharing #14235 use the same import path, so this helps attribute remote-hit local materialization too; it does not duplicate those features. It is instrumentation, not a speedup. |
| `677da74a1e`, builtin image wcprof boundaries | Keep as observability | Separates copying compressed builtin blobs, metadata and rootfs import. Preserves the builtin-content lease and import flow. Distinguishes SDK image extraction from registry network fetches; helpful for both plain cold and remote-hit benchmarking. No claim that it reduces latency. |
| `f14419ac42`, bundled TS runtime uses committed Go bindings | Keep, with normal SDK release/CI validation | Migrates only the engine-packaged runtime from legacy `dagger.json` to `dagger-module.toml`, keeping name and engineVersion. `useRuntimeCodegen` already selects the committed-files path for TOML, so this removes actual redundant runtime binding generation without introducing another cache. Runtime source folder packaging includes the new TOML recursively. User SDK generation remains separate. Existing validation covers real calls and source edits; cross-platform engine-payload builds and a generated-bindings freshness check are still appropriate upstream. The measured cold win is removal of one SDK codegen execution; large first-pair wall gains include unrelated image variance. Warm did not improve measurably. |
| `64be200d28`, archive-parent reuse | Keep evidence; do not enable prototype | This commit contains a disabled external containerd patch and benchmark evidence, not runtime production changes. One-entry parent reuse reduces repeated sibling path walking; tests cover symlink/whiteout/custom callback cases. Isolated imports improve, but complete quiet cold runs stay around26s and warm is unchanged. Upstream containerd is the right API review venue if revisited. No gain supports vendoring it into current Dagger stack. |
| #14181, reserved cache floor | Related open PR, **not included here** | `git diff d8f1f0d6d2 c12a34663b -- dagql/cache_prune.go` is empty; current minFreeSpace branch still lacks the final reserve clamp. Useful correctness fix for low-free-space users whose cache is continually pruned, not an explanation for this ~53%-full host's fresh-volume latency. Do not report it among retained gains. |

Sipsma PR state checked via GitHub: #14224, #14228, #14229, #14233, #14235 are
merged, already included in the rebase. #14241 remains open and adds verification,
fixture controls and CI; it is not another production cold fast path.

Other currently open fixes are complementary: #14251 removes stale in-memory
snapshot metadata after disk GC, addressing long-lived memory growth; #14121
squashes overly deep overlay parent chains and currently stats up to128 parents
per new snapshot. Neither removes the measured fresh SDK materialization/build
writes. No evidence justifies removing either overlapping lifetime or authorization
checks from our cache paths.

Follow-up independent experiment: GOTMPDIR on a Dagger temporary mount. Source
and build/output caching stay ordinary, but this changes memory demand and
requires constrained-memory validation before any default. No measured gain yet.

Links: https://github.com/dagger/dagger/pull/14241,
https://github.com/dagger/dagger/pull/14251,
https://github.com/dagger/dagger/pull/14121,
https://github.com/dagger/dagger/pull/14181.
