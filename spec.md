# Git `ls-remote` Session Cache Spec

## Context
- Multiple Git-related APIs (`git()`, `branch()`, `tag()`, etc.) call `git ls-remote --symref` eagerly inside `core.RemoteGitRepository`.
- In warm sessions this results in identical commands being executed several times (observed 4× `ls-remote` per module load, ~1s each) even when nothing has changed.
- Previous attempts to lazify `ls-remote` were blocked by:
  - Authentication discovery (SSH vs HTTPS and private repo detection).
  - Caching semantics: Github metadata must not leak between clients; multiple GraphQL calls should reuse the same result.
- Tech lead guidance (Justin) was to expose an internal DagQL field (e.g. `GitRepository.__lsRemote`) and use explicit `GetOrInitialize` caching through the DagQL session cache. This keeps memoization in the schema layer while letting the backend continue to manage auth/service setup.

## Goals
1. Deduplicate `git ls-remote` invocations within a DagQL session for the same remote + auth + service configuration.
2. Ensure no relaxation of existing auth/isolation guarantees. Private repo metadata must remain scoped to the client/session that fetched it.
3. Maintain compatibility for future "lazy `ls-remote`" work – the cached result should be reusable if we defer the call.

## Non-Goals
- Redesign of Git API layering (`core/git`, `util/gitutil`, etc.).
- Changing cold-start behaviour or fetch depth – focus on memoizing the metadata lookup.
- Cross-session persistence; cache stays in-memory per DagQL session.

## Proposed Design
### Hidden Schema Field
- Add `GitRepository.__lsRemote` (internal-only) field in `core/schema/git.go`.
  - Not exposed to users; intended for other resolvers via `dag.Select`.
  - Resolver returns a DagQL object representing the remote metadata (`*core.GitRepository.Remote`).

### Implementation Flow
1. **Resolver logic**
   - Retrieve current DagQL server + session cache.
   - Compute a cache key (string) that includes:
     - Resolved remote URL (`repo.URL`)
     - Auth token/header/socket digests (presence + digest) and HTTP username.
     - SSH known hosts (hashed contents) if provided.
     - Service bindings information (service ID digest + hostname + aliases).
   - Call `srv.Cache.GetOrInitialize` with that key to memoize the `ls-remote` result.
     - Store the cached value as a `dagql.AnyResult`/custom struct containing the serialized Remote (e.g. `*gitutil.Remote`).
     - On cache hit, clone the remote so consumers can't mutate shared state.

2. **Backend callback**
   - Within the initializer, invoke existing `RemoteGitRepository.setup` (services + auth) and `git.LsRemote` once.
   - Continue to rely on `gitutil.Remote` struct for data.
   - If auth fails, propagate the error – cached entries should represent either success or the failing error.

3. **Reuse in existing resolvers**
   - Update `core/git.go` / `core/schema/git.go` to load `__lsRemote` instead of directly calling `repo.Backend.Remote()` when metadata is needed.
   - Keep `RemoteGitRepository.Remote()` as a thin wrapper that simply selects `__lsRemote` (for backwards compatibility with existing callers). Eventually, centralize all usages through the hidden field.

4. **Concurrency & cloning**
   - Stored value should be immutable or cloned per return to avoid accidental mutation. `gitutil.Remote` contains slices and maps; deep-copy on retrieval.
   - Use `cache.ValueWithCallbacks.SafeToPersistCache = false` (we only keep it in-memory per session).

### Error handling
- Cache key should set `DoNotCache` to `false` so errors also get memoized (prevents hammering remote with repeated failing requests).
- Ensure errors include enough context but avoid leaking secrets (don’t print auth values).

## Tests
- Unit test covering `__lsRemote` caching behaviour (e.g. call twice, ensure underlying `git.LsRemote` executed once using injected stub).
- Integration test (if feasible) verifying `git()` call makes a single `ls-remote` against a local repo when multiple schema fields are accessed in the same session.
- Tests for cache key isolation: different auth token / service binding should trigger separate invocations.

## Migration / Cleanup
- Remove or revert any interim engine-level caching layers added previously for this task to avoid double-caching complexity.
- Document the hidden field and caching strategy for future maintainers (update developer docs or inline comments).
- Optional: expose helper in `core` to compute cache key so both schema and backend stay in sync.

## Open Questions
- Should the cached value be a DagQL object (`dagql.ObjectResult`) or a plain Go value stored in the cache? (Storing plain struct keeps dagql cache simpler but requires manual cloning.)
- Do we need eviction hooks when services/auth resources change mid-session? (Likely no – changes produce distinct cache keys.)
- Any telemetry desired to confirm memoization rate? (Could wrap initializer with existing tracing utilities.)

## Risks / Mitigations
- **Risk**: Accidentally sharing private repo metadata across clients due to insufficient cache key scoping.
  - *Mitigation*: Include client/session-specific auth identifiers in key and rely on DagQL session cache isolation.
- **Risk**: Hidden field becomes part of public API accidentally.
  - *Mitigation*: Prefix with `__` and omit from generated SDKs; add comment noting internal use.
- **Risk**: Errors cached might mask transient network issues.
  - *Mitigation*: Align with existing cache TTL defaults; consider TTL or manual invalidation if problematic.

