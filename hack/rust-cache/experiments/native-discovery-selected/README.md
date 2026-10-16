# Selected native package discovery

The [report](../../NATIVE_DISCOVERY_SELECTED.md) selects Rust-module da1ae47b6c96a3117de303b7584d028e35166530, replacing 3cd40e5928563ade3ea1cd21ab9924cd03d88fc3. The compiler tree is identical. The native backend remains experimental and opt-in; this does not complete the broader roadmap.

`paired` contains eight balanced randomized before/after/Cargo pairs for each of four workloads: 96 measured commands plus 12 preparation commands. Metadata records the random seed, workload-specific orders, module and engine revisions, all heap/CPU/pressure counters, and the fresh numeric source value for every run. Profiling stays off during timing. Every admitted observation is kept, including a candidate check overlapping snapshot collection.

`profiles` contains six separate diagnostic captures: engine/CLI CPU, CLI runtime trace, wcprof and bounded goroutine snapshots. Final wcprof captures have zero dropped events and open operations. Diagnostic timings are excluded from the paired comparison.

`validation/oracle` exercises sixteen discovery cases against Cargo on a fresh namespace. `validation/public-checks` verifies normal public collection checks through a source edit, invalid Rust, repair and reversion, with exact native compiled-result reuse. `cross-module` immediately requires 2/2 hits while switching between the original and candidate, with no preparation step. `validation/retained-cache` preserves initial hit counts and then demands complete reuse in all six older native histories.

`runs/selection.json` preserves all six fixture configurations before and after selection. Fixture source topology and the full diagnostic engine source replacements are archived in the preceding [dimension-key experiment](../artifact-dimension-key-fields/); update absolute paths when rebuilding. The selected engine binary hash is 4699d50526e3b2c358d0467c6cacc79aff1061b9295754648713a21104524c65. The source and patch here capture the exact module delta. The compiler directory is unchanged and available at the recorded Git revisions.

`upstream-review` records Sipsma's latest twenty PRs and the exact shutdown PR head. Its body is referenced by URL and SHA-256 rather than reproduced here. That shutdown patch is not applied. The initial output-parent failure is retained under `runs`; it ran zero benchmark commands. Binaries, cache volumes, targets and Git metadata are excluded.

Final state and validation status are in `runs/final-runtime-state.json` and `runs/status.json`. Direct dimension-key reads stay selected; temporary profiling and measurement controls are restored. There are still eight prepared Dagger proposals and no new upstream PR opened by this experiment.
