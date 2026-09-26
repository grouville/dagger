# Generic static TypeScript metadata: prototype boundary and automatic freshness

This directory is an **isolated, incomplete prototype**, not an upstream-ready default. Its engine guard is opt-in by generated sidecar. A TypeScript body edit currently invalidates the conservative whole-module manifest and fails closed. That changes normal development UX and must not be enabled upstream as implemented. A stale manifest must never fall back to the old committed `__dagger.entrypoint.ts`: that file contains both registration metadata and dispatch, and can itself be stale after an API edit.

The measured 2.643 → 2.132 s warm result belongs to the separately frozen frontend fixture under `../ts-static`; these generic files have no end-to-end performance result. The measured root Go test edits did not edit the TypeScript module. Nothing here establishes a 500 ms TypeScript API-edit loop.

## Existing authoritative path

The analyzer already produces all needed metadata. `sdk/typescript/runtime/introspector.go:emitEntrypointArtifacts` can run `ts-introspector` once and feed the same `TypedefModule` to both the existing TS dispatch template and the new Dang metadata template. The prototype generator does exactly this; it does not infer a schema from emitted JavaScript or introduce a second source parser.

`core/sdk/module_code_generator.go:Codegen` already:

1. scopes the exact immutable `ModuleSource` to the SDK operation;
2. obtains `deps.SchemaIntrospectionJSONFileForModule(ctx)` from the caller's actual dependency schema;
3. invokes the SDK `codegen(modSource, introspectionJson)` through DagQL;
4. returns one immutable generated directory containing source and generated bindings.

This is the appropriate regeneration authority and cache key. No timestamp, workspace path, TTL, or process-global schema map is required.

`core/schema/modulesource.go:runModuleDefInSDK` is the current metadata-selection boundary. It has the partially initialized module, immutable source, loaded dependencies, runtime implementation, and types implementation before installation. The prototype hooks there, but a production capability should live in the SDK interface/shared entrypoint contract rather than switch on `SDK.Source == "typescript"` in core.

## Safe automatic fallback

A generic SDK capability should return a **prepared module** with generated types and the matching execution source from one generation transaction. Conceptually:

```
prepare(source snapshot, dependency introspection, SDK identity)
    -> {metadata source, execution source/dispatch, description}
```

When the committed sidecar validates, return that pair directly. When it is missing or stale, call the existing SDK Codegen/analyzer on the changed immutable source and current dependency schema, consume the returned metadata, and bind **the same generated source directory** to execution. Do not export files to the user's checkout and do not call `asModule` recursively. Parent module default paths/addresses and workspace authority remain bound to the original module/workspace, not to an unrelated synthetic directory.

The engine must propagate the prepared source into the module's lazy runtime load. Calling the type fallback alone is insufficient: `moduleDefViaRuntime` and subsequent `runtimeImpl.Runtime` currently read `mod.Source.Value`, and the TOML no-codegen path intentionally trusts committed dispatch. A correct fallback must replace that execution input with the prepared result (or expose a runtime capability that accepts it). Setting only a temporary `staticSource.Entrypoint` for `types()` would return a fresh schema but execute stale dispatch after an API edit.

Generation should use `generatedCodeImpl.Codegen(ctx, mod.Deps, src)`, whose schema is already available here. Avoid `runGeneratedContext` as the fallback: it also generates clients, mutates module config and VCS files, and can trigger additional module loading. The exact generated directory's `SourceSubpath` must be preserved; `GeneratedCode.Code` is a context-root directory, not always the module root.

## Missing generic correctness work

- Pair metadata and execution inputs atomically, including source modules with dependencies and relative imports. Current local-file manifest does **not** establish freshness against a changed dependency schema if committed bindings have not changed. A production key must include the immutable dependency introspection content and SDK/emitter version.
- Finalize manifest after every generated input has been added. Current `sealStaticMetadata` runs inside SDK Codegen, before core may rewrite module config, `.gitignore`, and `.gitattributes`; consequently a whole-tree guard can falsely reject the final exported tree. Either define an explicit analyzer input closure plus canonical config/schema identities, or seal at the final directory boundary. Do not silently exempt unknown inputs.
- Conservative validation of all local inputs is a correctness-first proof, not the desired algorithm. Changed implementation bodies can reuse unchanged metadata once the analyzer proves the exported API is identical; that proof must also update execution source and avoid replaying stale source-bound results.
- Keep imports, optional/list/enum/interface/default/decorator semantics on the existing analyzer path, with generated schema parity tests. Unit parsing of emitted Dang does not prove equivalence to the engine schema.
- Retain the shared ModuleEntrypoint `types`/`call` direction used by Go/Java/Python SDK work. The current types-only Dang adapter deliberately raises if `call` is invoked; runtime calls continue through the original TS runtime under the generic engine overlay. It is not the final shared call adapter.
- Add actual analyzer → generated directory → engine registration → call tests for two distinct modules, changed dependency API, TypeScript body edit, added/removed/renamed API, settings/defaultPath, and restored source. Re-run timings on the fallback; it may be slower than committed unchanged metadata.

## Why not turn on this guard now?

Failing closed demonstrates that the optimization cannot silently expose stale schema. It does not preserve UX. The upstreamable pieces at this stage are the emitter and its semantic coverage, plus a design of the SDK preparation contract. Enabling the engine hook requires the atomic automatic fallback and the integration matrix above.
