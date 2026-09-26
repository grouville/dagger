# Constructor caching audit: preserve source and image freshness

Read-only audit, 2026-09-25. An optional source-only patch is prepared; it has not been generated, executed or timed. No existing fixture, shared source or public module reference was changed.

## Recommendation

The Backend constructor is a reasonable narrowly scoped candidate for ordinary Dagger caching: its body only returns `&Backend{Source: source}`. It reads no clock, randomness, environment, filesystem or network, and calls neither `dag` nor current workspace state. Its contextual Directory argument is loaded and hashed by the engine before cache lookup.

Do **not** blindly flip caching for all backend functions. `GoTestBase` and `goBase` resolve the mutable image tag `golang:1.26-alpine` inside their bodies. The engine intentionally resolves tag references per session. Caching an enclosing function's completed container result can retain an already-resolved image; preserving the existing freshness contract requires explicit session policies unless image identity is made a real immutable input. The same concern applies to exported Build, Binary, Container and Serve, which call these helpers transitively.

`constructor-only-source.patch` opts the backend module into ordinary default caching but marks every current exported body function `+cache="session"`: Build, Binary, Container, Serve and GoTestBase. Only New (and already-pure object field access) gains broader reuse. It layers on the previously measured compiler-cache-mount prototype, changing no source filter, image, service binding or build command. Future exported functions would need the usual author review under the module's new default.

This may remove one ~84 ms runtime invocation on unchanged inputs. It cannot remove schema/runtime registration or the explicitly retained per-session GoTestBase call. No speedup is established yet, and content edits should invalidate the constructor normally.

## Why the old opt-out exists

Local Git history provides concrete provenance:

- `66c4ccec06c6a2cdc6fea9eb2c9d9f13feef42cb`, 2026-08-05, `beta.9 migration`, created `.dagger/backend/dagger-module.toml` with engineVersion v0.18.7 and disableDefaultFunctionCaching=true. Its preceding dagger.json used v0.18.7 and had no such explicit flag.
- `3b4e0b67d5d9d0238574b76c2439413df4c38fa3`, 2026-09-23, moved/simplified modules while retaining the flags.
- `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`, 2026-09-23, changed engineVersion to v1.0.0-0, retaining the opt-out in backend, frontend and greetings.

The engine's MinimumDefaultFunctionCachingModuleVersion is v0.19.4. The old backend v0.18.7 predates it. Migration code preserves the opt-out, and source loading respects explicit configuration before version defaults. This supports a compatibility origin; history contains no backend-specific stale-source fix explaining the flag. It does not prove the author intended a later blanket opt-in.

The local TypeScript frontend also has the opt-out. Its constructor only saves an explicit Directory, while serve resolves the mutable `nginx` tag. Greetings' constructor calls backend/frontend constructors through Dagger, so it needs transitive policy/dependency analysis rather than being treated as a trivial holder. Do not switch all three modules together for timing.

## Why host changes still belong in the cache key

The current source path is explicit:

1. `ModuleFunction.DynamicInputsForCall` identifies defaultPath arguments and calls `loadContextualArg` before executing the module function.
2. `ModuleSource.LoadContextDir` resolves from the bound workspace (including overlays) or module context, applies ignore filters, and ensures a content digest on the Directory.
3. `DynamicInputsForCall` installs that Directory ID using `CallRequest.SetArgInput`, so it participates in the semantic call inputs before lookup.
4. `Workspace.directory` is client-scoped. Host import obtains the current client's attachable connection and filesync mirror; the returned immutable Directory carries the snapshot content digest. A content-equal result can be reused after the current input is resolved, without substituting another client's live filesystem.
5. Handle-form result IDs are resolved against the current session in `resultCallRefFromIDInput`. This patch changes none of that ownership/admission logic.

Therefore the proposal is not a TTL over live paths, skipping filesync, retaining workspace IDs across commands or deleting client scoping. Source bytes are still required as input. Backend.New then returns the explicit Directory as a normal owned module field. The broad source filter can make unrelated edits invalidate the constructor, but it is deliberately unchanged here.

Service values and running processes are also distinct. Service bindings persist owned Service result references; Services.Get/startWithOpts keys running instances by current SessionID (and ClientID where needed). A container/service recipe may be reusable while the process lifecycle remains session-managed. The conservative candidate retains session policy on all service-producing functions anyway.

## Existing cache annotations cannot opt one function back in

Go codegen recognizes:

| Annotation | Engine policy |
| --- | --- |
| No cache pragma | DEFAULT |
| `+cache="session"` | PER_SESSION |
| `+cache="never"` | NEVER |
| `+cache="40s"` (valid duration) | DEFAULT with TTL |

`Function.derivedCachePolicy` converts DEFAULT to PER_SESSION whenever the module opt-out is true, regardless of whether a TTL was explicit. Consequently a positive-duration annotation is not an escape hatch under the old module-wide flag. `+cache="default"` is not the syntax either: it would be parsed as an invalid duration. This follows current implementation, not an inferred convention.

TypeScript's `@func({cache: "session" | "never" | duration})` and Dang's `@cache(policy: ..., ttl: ...)` converge on the same engine policy. After a module-level opt-in, explicit session/never annotations provide exclusions. This is an SDK-wide policy shape, not a Go-only limitation.

## Generation is part of correctness

The optional patch changes source comments and config only. The v1 Go runtime uses committed generated files on its no-runtime-codegen path. The existing backend `dagger.gen.go` has no WithCachePolicy registrations for these functions. Merely applying the comments and flipping the config would accidentally enable ordinary caching for the body functions too.

Before any candidate run:

1. Copy the preserved cache-mount candidate into an isolated workspace.
2. Apply the source-only patch.
3. Run the normal Go SDK generation workflow for the backend. Do not time regeneration as an unchanged warm check.
4. Verify generated registration contains PER_SESSION for exactly Build, Binary, Container, Serve and GoTestBase, while New remains DEFAULT. Preserve +up on Serve and defaultPath/ignore on New. Check generated source maps rather than hand-editing metadata.
5. Then load it and confirm with wcprof that warm cross-session constructor calls can hit while GoTestBase still executes once per session.

No new pragma or schema feature is proposed. The existing adding-pragmas workflow was read to ensure source annotations reach generated metadata.

## Correctness and performance plan

Use the existing baseline and an isolated candidate; never mutate the published app to obtain a result.

- Exact `check -l --all` output and scoped dimension flags must match before and after. Ordinary `check -l` must remain static.
- Fresh CLI sessions with unchanged source: record constructor/goTestBase call outcomes separately. Warm full-command timings alone do not show which work disappeared.
- Real production edits, embedded greetings.json edits, test edits and restore: execute checks and assert their expected outcomes. A changed HTTP sentinel in the compiled API must fail, then fresh restored source must run all six tests without skips.
- Confirm a new session can actually consume the returned API-bound container after the prior session is closed, using a distinct consumer command argument. This must start a current-session service rather than passing because the final test result was cached.
- Exercise an alternate explicit Source Directory, nested workspace cwd and a workspace overlay. Source identity and ignore filters must survive constructor reuse.
- Verify mutable-image policy remains PER_SESSION in generated metadata and call keys. A separate local registry tag-movement fixture can prove freshness without depending on changes to a public tag; do not repush or mutate public images.
- Measure five paired warm runs and five distinct edit→check pairs after generation/initialization, profile separately, and report first fill separately. No 84 ms wall-time saving is promised by source inspection.

## Independent small multi-SDK regression fixture

The existing greetings experiment is a credible real-user workload: a mixed Go/TypeScript/Dang workspace, actual API service, selected and batched tests, source edits, error propagation and six-test restoration. It is insufficient evidence for every SDK's constructor caching or all source kinds. The measured 69% gain specifically fixes missing compiler caches in this backend recipe.

Add a tiny table-driven Go/TypeScript/Dang fixture independent of greetings:

- Each module has a constructor accepting `Directory` via defaultPath and an ignore pattern, storing only that explicit object.
- A pure `read` returns marker.txt. A `check` fails unless marker.txt contains the expected fixed sentinel. No language build tools, container images or external network are needed inside these functions.
- With ordinary caching enabled, read marker A; run a second CLI/session and read A; edit to B and read B; change to a failing marker and require check failure; restore and require success.
- Repeat against two client workspaces with the same module name/layout but different marker content. Neither may see the other's result. Repeat after the first client disconnects.
- Add a same-session case like existing TestDefaultPathNoCache, and a workspace overlay case, to distinguish a cached module value from a live source provider.
- Confirm ignored-file edits leave the observed source content unchanged, without relying on a performance threshold.
- Keep a separate explicitly PER_SESSION method that returns a per-session diagnostic token in a test-only fixture to verify the exclusion is honored. Do not add randomness to the constructor under test.

Use the fixtures for generic correctness, then keep actual edit→check benchmarks on realistic projects. A tiny fixture is useful for isolating fixed SDK/runtime costs; it cannot replace the service/compiler workload or prove its performance.

## Source references

- `core/modfunc.go`: cacheImplicitInputs, DynamicInputsForCall, loadContextualArg.
- `core/modulesource.go`: LoadContextDir and content hashing.
- `core/typedef.go`: derivedCachePolicy and persistence/TTL policy.
- `core/schema/modulesource.go`: explicit opt-out precedence.
- `core/schema/host.go`: current-client filesync and content digest.
- `core/schema/workspace.go`: currentWorkspace per-call identity and directory client scope.
- `core/schema/container.go`: fromSessionScopeInput for mutable tags.
- `core/services.go`: session-keyed running-service lifecycle.
- `core/service.go`: persisted/owned service bindings.
- `core/sdk/go_sdk.go`: committed generated metadata runtime path.
- `cmd/codegen/generator/go/templates/module_funcs.go`: cache pragma emission.
- `core/integration/module_runtime_behavior_test.go`: cache policy tests across Go/Python/TypeScript.
- `core/integration/module_path_inputs_test.go`: existing defaultPath source-change regression.
