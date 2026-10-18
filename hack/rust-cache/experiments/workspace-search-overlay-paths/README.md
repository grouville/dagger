# Host-overlay search regression and fix

The standalone fix is [pushed to the fork](https://github.com/grouville/dagger/tree/fix/workspace-search-host-overlays), commit `744ec940`, directly on main `ff0b029a`. No PR is open. See [the assessment](../../NATIVE_WORKSPACE_SEARCH_OVERLAY_PATHS.md) and [review description](../../upstream-prs/workspace-search-overlay-paths.md).

`evidence.tar.gz` includes the direct GraphQL reproduction, the new regression's failure on main, the scoped race checks, real integration failures and passes, source overlays, standalone source, deployment records and all six native-cache histories before/after replacement and after the Go cohort. The initial whole-file identity assertion is retained; the search-function comparisons establish the actual source equivalence.

`MANIFEST.json` records every member's size and SHA-256. All **256 members** were read back and verified. Large executables are excluded. Recorded absolute worktree paths can be recreated or adjusted to the corresponding archived sources.

The shutdown stack observation concerns a possible later persistence experiment; it is not a measured improvement or part of this fix. The native search fix preserves telemetry and ordinary GC, uses the same retained volume and introduces no shared cache or locks. Its standalone integration test covers overlay-only, mixed, parent-directory and genuinely missing paths.
