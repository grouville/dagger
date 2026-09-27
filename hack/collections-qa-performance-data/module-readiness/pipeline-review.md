Prepared source review; readiness timings are still pending. This is not an implementation proposal with an established saving.

Current dependency chain:

1. `core/schema/artifacts.go:collectArtifacts` asks `workspaceTargetModules` for the complete selected module set.
2. `engine/server/session_workspaces.go:ensureModulesLoadedModeWithSuccess` holds `client.modulesMu` while resolving the batch in parallel. Whole jobs are bounded to eight.
3. After every job completes, the loader collects deterministic failures, deduplicates sources/settings, arbitrates entrypoints, then acquires `stateMu` and publishes the resolved modules and required entrypoint dependencies. Only then are pending entries removed and workspace modules considered served.
4. `collectArtifacts` builds per-module trees, SDK-managed trees, include filtering, global artifact path validation and deterministic sorting. The returned Artifacts object contains metadata, not constructed module values.
5. CLI dimension handling requests expanded items in a later query. Expansion constructs the Go root, which evaluates the typed address `dag://backend/go-test-base`, then discovers Go modules and tests.

What the new profile can prove: resolve-ready times for `go` and `backend` relative to the end of the catalog. The larger of those times gives an optimistic earliest point when this collection's two known module definitions could be available. Catalog-end minus that value is an **upper bound on the all-modules barrier opportunity**, not a guaranteed reduction. The query gap is separate; combining requests cannot erase actual computation. Recompute this on the future Go static-metadata stack: removing registration processes can shrink the opportunity itself.

Why putting expansion inside today's resolution goroutine is unsafe:

- It would execute while modulesMu is held. The dynamic backend address follows `resolveWorkspaceArtifact` → `collectArtifacts(include: backend/...)` → on-demand module loading, which needs the same owner's loading state. Awaiting nested demands under the batch lock can deadlock; creating a new goroutine does not remove that dependency.
- A resolved module can be installed in a standalone DagQL server using `dagqlServerForModule`, but that does not publish sibling workspace modules or satisfy workspace-bound Address resolution. Changing current workspace or ClientScope to reach them would violate authority.
- Publication has semantic work: settings-aware source deduplication, extra-versus-ambient and blueprint entrypoint arbitration, versioned dependency installation, and deterministic failure handling. A late module can change the final root schema or surface a duplicate artifact path. Arbitrarily publishing whichever job finishes first makes behavior timing-dependent.
- The CLI's dimension aliases are global across the requested schema. Filtering can narrow enumeration only after alias resolution; an optimization must not guess which same-named dimension the user meant from the first module available.
- Load errors may be repairing/best-effort instead of fatal; collection enumeration errors have their own behavior. Starting arbitrary user collection functions before a later static validation failure changes what work executes on an invalid command.

Smallest plausible staged design, **only if the measured window warrants it**: maintain per-request immutable resolution futures separate from committed served-module state; validate all configuration-level naming/entrypoint decisions available without execution; perform static tree construction as each resolved module arrives; publish the authoritative batch exactly as today; then construct collection receivers. This first stage overlaps only static tree work, expected much smaller than the ~694ms dynamic expansion and must not be advertised as overlapping that whole phase.

To overlap actual collection receivers would require a larger demand coordinator: Address/default resolution must be able to await a selected sibling's resolution future and evaluate it through the original workspace authority in an isolated schema, while preserving final publication and conflict/error semantics. Known, globally unambiguous module-qualified paths are the plausible starting subset. Cross-module dynamic defaults, extra/blueprint entries, alias ambiguity, overlay config edits, cyclic addresses, cancellation and retries are mandatory regression cases. No global cache or persistent snapshot is needed, but this is not a one-line errgroup optimization.

Alternative lower-risk concrete work remains independent: use existing upstream static SDK metadata to remove four registration process launches; integrate the already-measured local cwd helper; investigate order-preserving parallel independent root validation; use name-only filesystem discovery where marker content is not required. No new broad caching policy is justified by this barrier alone.
