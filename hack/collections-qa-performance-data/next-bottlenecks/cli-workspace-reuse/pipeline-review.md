# Static discovery to collection expansion: dependency/barrier review

Source review, 2026-09-25. No pipeline implementation or timing claim yet.

## What the observed 630 ms + 745 ms represents

The latest TypeScript-static profile supplied by the parent reports a roughly 630 ms static Workspace.artifacts query followed by roughly 745 ms in Artifacts.__itemsJSON. The latter includes configured backend construction/base resolution (~266 ms), Go.modules (~290 ms) and test discovery (~120 ms). These are actual dependency phases. Combining two HTTP requests does not make the latter independent of the former.

The source chain is:

1. `runChecksCommand` → `commandArtifactsWithFlags` → `commandArtifacts` pins a workspace and constructs the lazy `Workspace.artifacts(...).filterCheckCommand(...)` selection.
2. `listArtifactSelection` → `readListedArtifacts` materializes `selection.ID()` before sending the separate `__itemsJSON` projection.
3. `workspaceSchema.collectArtifacts` → `workspaceTargetModules` → `workspacePrimaryModules` → `EnsureWorkspaceModules` → `ensureModulesLoadedModeWithSuccess` resolves the demanded workspace modules.
4. `resolveModuleLoadBatch` runs module loading in parallel, with the existing parallelism limit, but **joins all loads** before returning.
5. `ensureModulesLoadedModeWithSuccess` then deduplicates/arbitrates entrypoints, serves the whole batch, removes successful pending entries and releases the module lock.
6. `collectArtifacts` builds each loaded module's artifact tree using `ModuleArtifactNodes` / `NewModTree` / `ArtifactNodes`, adds SDK generator artifacts, sorts, validates duplicate paths and returns the complete static catalog.
7. `filterArtifactCommand` applies check/generator policies. `__itemsJSON` finally calls `expandArtifacts` → `Artifacts.Expand`; request-local shared-prefix expansion is already parallel across independent templates/parents.

There is no existing streaming or per-module ready callback in that chain. A consolidated `Workspace.__checkItemsJSON` field that merely calls the same functions sequentially saves projection/transport overhead, not the reported 745 ms of collection work.

## The lock/publication constraint

`ensureModulesLoadedModeWithSuccess` holds `client.modulesMu` from entry through the full parallel resolution batch, arbitration and schema serving. It only takes `stateMu` near publication. The existing onSuccessLocked callback deliberately runs while modulesMu remains held; it is not a hook for arbitrary module execution.

Starting collection expansion from a loader callback can resolve another workspace artifact. Kyle's Go constructor does exactly this through its configured `base=dag://backend/go-test-base`. That resolution may demand another workspace module and need modulesMu. Waiting for it from the loader callback creates a lock cycle; launching without joining merely postpones it until global publication and may gain no overlap. Likewise, serving modules as they finish can change entrypoint deduplication/conflict semantics and make a partially published schema visible to unrelated queries.

A real per-module pipeline therefore needs explicit module readiness and resolution dependencies, not a goroutine added inside the existing batch loop:

- Reserve per-session module-load futures under modulesMu, then perform SDK/source loading without holding that lock.
- Key futures by the same module request/source/settings/client authority semantics as the existing load path, retaining transient-cancellation retry and deterministic failure behavior.
- Let a module's private artifact tree depend on its resolved Module result and default dependencies; another configured workspace address waits on the corresponding module future, without waiting while holding modulesMu.
- Preserve atomic entrypoint arbitration/publication rules. A private discovery result must not silently become a partially served global schema.
- Keep saved Artifact/Artifacts dependency wrappers and persisted module/workspace references valid; avoid passing raw runtime objects around outside DagQL ownership.

This is architectural work across the session loader and artifact discovery. It complements, rather than replaces, SDK static definitions and deferred constructor arguments.

## What may safely pipeline, and what must wait

For `check -l --all` without dimension filters, collection keys do not require every unrelated SDK's type definition mathematically. Final rendering still needs all global dimension aliases. That creates potential overlap if a selected module's schema is ready before slower independent modules.

However, the current metadata barrier also establishes observable guarantees:

- `prepareArtifactDimensionFlags` can register unknown long names cheaply, but `commandArtifactsWithFlags` validates aliases against the complete selected schema scope before expansion. A later module can make an earlier short alias ambiguous. Raw URI queries bind in their own path scope; CLI flags bind in the combined path scope.
- `collectArtifacts.validateArtifactPaths` rejects ambiguous artifact paths before any collection receiver is evaluated. Entrypoint-exposed paths can collide with another module's namespace. Expanding first and checking ambiguity later changes which user functions run for an invalid request.
- Generator/check filtering includes workspace settings, wrappers replacing raw generator namespaces and accumulated skip policies. `artifactGeneratorPolicies` compares implementation/context-source identities across entries; it cannot be replaced with a per-module guess.
- Ordinary `check -l` without --all must remain static. A speculative expansion would undo the UX fix from the original collections thread.
- Expansion errors, best-effort module-load failure artifacts, deterministic row order and cancellation remain part of the result contract.

A conservative first pipeline can limit early work to modules whose namespace is proven disjoint and whose selected non-generator checks have all dependencies and policies resolved. It should defer ambiguous aliases, entrypoint collisions and cross-module generator policy cases. A slower-path fallback is acceptable; speculative evaluation on invalid/excluded selections is not.

Measure module-ready times before estimating savings. The overlap ceiling is the portion of independent expansion whose inputs are ready while other demanded metadata remains outstanding. Neither the whole 630 ms nor the whole 745 ms is automatically recoverable.

## Smaller prepared fix: share the command's workspace root

The current formatter calls `dag.CurrentWorkspace().Artifacts().ID()` again after reading expanded items, solely to obtain globally unambiguous dimension aliases. `currentWorkspace` has a new identity on every call. The selection helper pinned one workspace already, but did not share it with formatting.

The prepared CLI overlay returns that pinned workspace alongside the selection and passes it to `listArtifactSelection`. Global alias formatting still uses an **unfiltered** `ws.Artifacts()` catalog; it now shares the same workspace identity and, for an unfiltered command, the already-discovered catalog call. The scope is one command only. It does not retain host data across calls or remove global alias validation.

All list surfaces using this helper are wired consistently: check, up, generate, shell and agent. Pure agent composition discards the additional returned workspace because it does not render this listing. The test uses independent Go, TypeScript and Dang dimension identifiers with colliding aliases, including a nested module/test chain, and checks that qualified global aliases remain necessary even for a filtered module. A no-dimension case must not load a global catalog just for formatting.

This removes redundant discovery work; it is not the per-module pipeline above. No performance estimate is assigned before benchmarking.
