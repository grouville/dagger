# TypeScript registration experiment

The complete warm profile runs the **same frontend TypeScript registration twice**, once directly and once as a greetings dependency. They execute `/src/.dagger/modules/frontend/__dagger.entrypoint.ts` under `ModuleSource.asModule`, both beneath `Workspace.artifacts`; process time is 751.71/749.74 ms and overlaps. Removing both targets roughly this overlapping window, not 1.5 seconds of command wall time. No new timing is claimed before the experiment runs.

## Work already done at generation time

- `sdk/typescript/runtime/introspector.go:37` runs the TS analyzer once to produce `/work/typedef.json`, then calls the Go entrypoint emitter.
- `cmd/codegen/generator/typescript/templates/entrypoint_typedef.go` already represents every object/function/argument/pragma/source map needed for metadata.
- `cmd/codegen/generator/typescript/templates/src/entrypoint/register.ts.gtpl` emits literal TypeDef construction in `__dagger.entrypoint.ts`.
- `.../dispatch.ts.gtpl` still imports/evaluates the normal runtime SDK and the user's module before it recognizes the empty parent name as registration.

This is not a proposal to add a second TypeScript source analyzer. The metadata has already been analyzed; the remaining cost is starting a full language runtime to convey those generated literals to the engine.

The in-flight [Go SDK #36](https://github.com/dagger/go-sdk/pull/36), [Java SDK #19](https://github.com/dagger/java-sdk/pull/19) and [Python SDK #33](https://github.com/dagger/python-sdk/pull/33) use the shared `ModuleEntrypoint.types`/`call` direction. The current reviewed TS open PR [#63](https://github.com/dagger/typescript-sdk/pull/63) addresses collections, not static metadata delivery.

## Smallest isolated proof

The copied greetings workspace adds `.dagger-static-types/main.dang` to the frontend module. It reconstructs exactly the generated frontend object's constructor, source field, build/serve return types, @up and source maps. The file is a pinned fixture, not a general TS emitter.

An engine overlay loads only its `types()` with the existing Dang entrypoint driver. Calls keep the original TypeScript runtime and generated dispatch. The sidecar `call()` deliberately raises if accidentally used. There is no new container builder, cross-session runtime or retained evaluator, and the old IncludeSelfInDeps choice is preserved.

The overlay is gated to the fixture module name and a versioned manifest. The manifest pins the complete 19-file frontend module tree, including source, compiler config, package/lock, generated SDK, generated TS dispatch and module configuration. It also pins the sidecar. Files are read through the immutable Dagger source directory; there are no host mtimes or absolute checkout reads. Added, removed or changed inputs cause an explicit `static TS metadata stale` error. Unrelated application/Go edits keep the same metadata and should continue through the fast path.

This guard intentionally reads 5.66 MB per load in the first version. It is conservative and may cost some of the savings. A production generated artifact should use Dagger's input identities and dependency projection, not permanently hash every file through an ad-hoc mechanism.

## Freshness limitation and upstream path

Current `runtime_node.go:144` says the no-codegen TOML path trusts committed `sdk/` and `__dagger.entrypoint.ts`; it does not validate the latter against edited TS APIs. Falling back to that file on a sidecar mismatch would silently retain stale metadata. The experiment therefore fails explicitly on a TS metadata input edit. It is not yet the final no-manual-regeneration edit UX.

To upstream, extend the existing TypedefModule emitter to output a common static entrypoint, with an automatic generation path keyed on the actual analyzer inputs. A missing/stale artifact must run the authoritative TS analyzer and make the newly generated types available immediately. It must not just instruct users to regenerate manually or reuse a stale manifest. Calls can then adopt the existing JSON entrypoint protocol, preserving exact argument coercion, rebuild/serialize, errors, cache/collection/decorator metadata and client scope.

A source-only body edit initially may regenerate conservatively. Avoid narrowing this to a home-grown regex/API hash: computed defaults, decorators, imported enums/type aliases and compiler resolution can affect metadata. A later semantic metadata digest can be produced by the existing analyzer itself.

Required proof matrix: unchanged listing parity; original frontend source/function dispatch; unrelated Go edit with changed rows; source change rejection; new source file rejection; config/generated client change rejection; restored input recovers; automatic API fallback once implemented. Cold and warm timings must keep the same services/checks and be reported independently of the existing SDK prototype stack.
