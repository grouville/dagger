# Explicit dependency plans for anonymous Git admission

A user-owned dependency plan could start required anonymous Git advertisements earlier without reading an inaccessible parent's cached configuration. It must be a declaration of permitted speculative network work, not a stored proof of repository access. I would first build a narrow local-fixture proof of that contract, not introduce a general lockfile graph into production yet.

The measured opportunity is roughly 160–191 ms earlier completion of the last advertisement in an ideal rescheduling of the saved seven-request sets. That is useful, but does not establish an equivalent command saving or make a 1.4 s listing a 500 ms listing. Existing Go SDK static metadata and the already-validated module path helper remain simpler ways to delete work.

## What the current path guarantees

`core/schema/modulesource.go:loadConfiguredModuleSource` reads the module's actual config through `ModuleSourceFS`, initializes it, and only then resolves its declared dependencies and SDK. This is why a child URL can become known after its parent has already waited on Git. Source kinds and access boundaries are shared across host, Git, Directory and Workspace sources.

`core/schema/git.go:cachedPublicRemote` already singleflights the anonymous advertisement by session and exact remote URL, except for service-bound Git. It retains the immutable advertisement, not just a public/private bit. `Query.git` separately controls implicit credentials: arbitrary nested code cannot use the host's credentials; trusted dependency resolution can consult the permitted caller contexts. A pinned commit is not an access grant. Probe errors also have an existing special case when a workspace pin permits later operations without contacting the repository; preserve that behavior.

`core/workspace/lock.go` currently records Git/ref and vanity lookup tuples, not dependency edges. Its repository lock identity deliberately omits transport. That scheme-less identity is appropriate for pins but is insufficient to authorize a speculative network request: a plan must distinguish the actual endpoint, transport and resolution context.

## Smallest useful contract

The proposed record is an optional, versioned **anonymous admission plan** in user-owned workspace metadata. It would describe known static relationships. It would neither provide dependency results nor replace normal lock entries. An engine-global result or a cached remote parent's private config must never be the source of this record at command startup.

Conceptually it needs these fields; this is a data-model sketch, not a proposed wire encoding:

| Part | Required identity |
| --- | --- |
| Plan | Format/resolver version, explicit speculative-contact policy, digest of the effective dependency/SDK configuration and relevant lock inputs |
| Root | Current workspace module/SDK name and source declaration, exact selected root, source kind, resolved immutable repository commit and config subpath when remote |
| Node | Repository identity, exact commit, config path and config blob digest, normalized declaration digest; local nodes use the current authorized configuration content, not a stale host stat |
| Edge | Parent node, static dependency or SDK role/name, original declared source, child node, exact anonymous probe endpoint and the resolution/vanity inputs which produced it |
| Reachability | Root-to-edge relationship sufficient to traverse only the roots actually demanded by the current command |

Do not key this graph by all application source bytes. An ordinary comment edit should retain a plan if dependency configuration, selected roots, lock pins and resolver inputs are unchanged. Conversely, a changed `dagger.toml`, module config, SDK mapping, pin, relevant environment/override or resolution rule must invalidate the affected plan. Dynamic runtime-discovered edges are outside the first version; observing one during an earlier execution does not prove it is required next time.

Initial scope should be exact HTTPS Git endpoints without embedded credentials and without service bindings. No SSH-agent use, credential-helper call, secret-bearing URL, private DNS/service startup or file transport may be triggered speculatively. This is a restriction on the first implementation, not a new meaning of ordinary Git source support. Use the existing transport/parser and normal vanity resolution before a prefetched result becomes usable. A plan does not authorize skipping vanity freshness or redirects; either their current endpoint agrees or normal resolution proceeds.

## Admission and publication are separate

1. Read the plan through the current workspace's ordinary caller authority. Determine the actual root load set using the existing command demand/selection machinery. A flat union of all historical lock entries is not an eligible set. `ws ls` and core-only calls should not acquire module work merely because a plan exists.
2. Match the effective root configuration and immutable pins. Compute the reachable static endpoint set in O(V+E), deduplicate exact endpoints, and launch a bounded number of anonymous probes. Keep a strict work/size cap; do not turn a large lockfile into unbounded parallel networking.
3. Continue the normal source-loading path concurrently. Parent access, config loading, dependency interpretation, ownership and SDK selection remain authoritative. An early advertisement must not publish a module, materialize a private config, install a schema or satisfy a parent's access check.
4. When ordinary resolution reaches an edge, verify its parent commit/config identity and declared child endpoint, then join/reuse the existing session-local `cachedPublicRemote` result. A mismatch discards the optimization and follows normal resolution. Static dependency loading errors and schema/entrypoint collision arbitration retain their current order and publication barrier.
5. A private result only avoids repeating the anonymous probe. It does not choose credentials early. The real demand performs its usual trusted-resolution/parent-client credential lookup. Results expire with the existing session, including negative visibility; nothing becomes a cross-session authority cache.

The natural scheduling hook is the current selected module-load batch in `engine/server/session_workspaces.go`, after root demand/configuration is known and before its workers await nested sources. The edge-validation hook belongs beside `loadConfiguredModuleSource`/`ResolveDepToSource`, not inside generic cache restoration. `collectArtifacts` also loads SDK-managed generator trees, so its selected roots cannot be guessed solely by an artifact's final path prefix. Reuse the effective load set which the engine actually chooses.

Keep original ordering and aggregate error collection. Prefetch errors for edges never demanded must not fail the command, overwrite a lock or turn into a module-load failure. Ordinary demand must still see its normal pin/error semantics.

## The decisive counterexample

Suppose a recorded root `A@commit-old` declares a child on a private/internal endpoint. The current command instead selects an unrelated root, or a branch/refresh resolves `A@commit-new` which removed the child. Starting all old graph entries contacts that child despite the current program having no reason to do so. Dropping the result later cannot undo the network request. Matching a historical parent SHA is not enough if it is no longer the currently selected root/pin.

Even with an unchanged root pin, the user may have lost access to A since the plan was written. Normal loading would fail before discovering A's children. Speculation can still contact the user-declared child before that failure. Therefore one cannot promise both “same network observations as the ordinary resolver” and “all transitive probes start before parent admission.” The record must explicitly permit those anonymous contacts for reachable selected roots, including the case in which later parent validation fails. This can be a documented format/feature contract; it does not imply an interactive permission prompt for each command.

If that contract is unacceptable, the transparent alternative waits for each parent admission/config validation before launching its child edges. It preserves the dependency waves, so most of the proposed benefit disappears. A signature, immutable commit or remote cache receipt establishes content provenance; none independently establishes present caller access or permission to contact an otherwise-unused endpoint.

Mutable branch/update handling follows the same rule. An ordinary command may use its current valid lock pin; `--refresh`/lock-update must not treat the old graph as a new pin. If a required endpoint becomes public/private during one command, the same per-session first-advertisement policy remains the boundary; starting it earlier changes when that existing observation is made, not its lifetime.

## Cancellation and cache ownership

Use the existing arbitrary-cache shared-work machinery rather than a detached fire-and-forget goroutine. `dagql/cache_arbitrary.go` detaches initializer cancellation under a client shared-work lease, cancels when the last waiter leaves, and removes failed/unowned entries. A speculative waiter and a demanded waiter must share that work; canceling speculation must not kill a probe still needed by ordinary resolution.

The scheduler must join its own workers on completion/cancellation without waiting for unused work longer than the session requires. It must not install an independent, shorter prefetch timeout as the lifetime of a probe already adopted by demand. Test the final-waiter race: a canceled speculative initializer must not leave an error entry or cancel a new demanded initializer for the same key. Existing cache logic addresses identity/lifetime, but the new caller needs an actual regression test around it. Do not persist advertisements or capabilities in the graph.

## What the saved measurements support

Both profiles followed an identical complete listing primer on the same retained diagnostic engine and volume. Unix was profiled first and Docker second. These are attribution observations, not an A/B estimate for a graph which does not exist.

| Observation | Unix profile | Docker profile |
| --- | ---: | ---: |
| Advertisements | 7 | 7 |
| Advertisement union/envelope | 385.63 ms | 384.95 ms |
| Longest advertisement | 194.23 ms | 225.22 ms |
| Ideal advance of last advertisement completion | 191.40 ms | 159.73 ms |
| Catalog | 589.20 ms | 620.76 ms |
| Expansion | 551.05 ms | 563.86 ms |

The ideal calculation moves every request to the first observed probe start while holding individual durations fixed. It does not subtract 385 ms from the command. It also is not a strict whole-command upper bound: downstream work on each branch and its actual critical path are not reconstructed here. Parent/config verification, graph availability and request contention could shrink the benefit. All seven requests reused connections; DNS/connect/TLS were absent. Request-write-to-first-byte dominates, so parsing or TLS tuning is not the large lever in these profiles.

The independent bounded module-load pipeline already demonstrated that moving the ninth source start ~147 ms earlier produced only ~24 ms earlier catalog completion in its one profiled pair. Earlier dispatch alone is not equivalent to equal wall-clock savings.

## Relationship to existing upstream work

These are the retained public descriptions retrieved at 2026-09-26T08:00:43.310759+00:00, not a new status check:

- [Yves #14015](https://github.com/dagger/dagger/pull/14015) removes duplicate per-client visibility and redundant pinned transport work but deliberately retains the first per-session check. The plan would schedule that same check earlier, not undo its freshness boundary.
- [Erik #14224](https://github.com/dagger/dagger/pull/14224), [#14229](https://github.com/dagger/dagger/pull/14229), and their transfer/live-offer stack preserve references, credentials, ownership and lazy byte acquisition. Those records are not a user-owned selected dependency graph and do not make cached private parent configuration readable before current admission. A plan must compose with their cache authority rather than bypass it.
- [Erik #14241](https://github.com/dagger/dagger/pull/14241) provides scripted Git/HTTP/cache restoration fixtures and integration coverage. It is a useful place to test the access-revocation and cross-engine cases, not evidence that the proposed scheduler already exists.
- [#14346](https://github.com/dagger/dagger/pull/14346) and [#14299](https://github.com/dagger/dagger/pull/14299) concern source ownership/client/Git dynamic inputs; retain those identities when matching a plan. This proposal must not cache a live host config by path alone.

No inspected retained description implements this exact opt-in graph. Distributed cache availability would not remove the per-session remote access observation by itself.

## Recommended next experiment

Do not implement a general transitive lock graph yet. First write a small, local-only proof using explicitly declared static HTTPS endpoints and a fake transport, on top of the existing session advertisement cache. It should demonstrate earlier child-probe start and unchanged final selected module/config output, plus these negative gates:

- Unselected roots issue zero requests; root/config/pin mismatch issues no speculative contacts unless the explicit contract permits them.
- A revoked parent never exposes cached parent configuration or publishes its child; optional speculative contact is accounted separately.
- Private probes request zero credentials; real demand retains the proper caller authority and same auth failure.
- Duplicate endpoints issue one session request; a new session performs a fresh request; service-bound/custom transport paths use the ordinary resolver.
- A branch refresh/vanity change invalidates plan use; application-only edits retain it; dynamic undeclared dependencies fall back.
- Cancellation, final-waiter races and deterministic errors leave no worker/session leak or poisoned future lookup.
- Restart/remote-cache restore cannot manufacture a graph from cached private contents or carry a prior visibility answer into the new session.

Only after those gates should one matched whole-command warm/edit trial determine whether the extra graph maintenance and explicit egress semantics justify the measured gain. The current evidence supports a potentially ~100 ms-class scheduling investigation, not a promised reduction or a default-on production change.
