# SDK and edit-loop audit, 2026-09-25

The complete greetings-api warm profile still runs two TypeScript processes (751.7 ms each, overlapping), six other runtime processes (574.4 ms aggregate) and 21 Dang invocations. These totals do not add into command wall time. The measured complete command remains 2.662 s median; no new latency result is claimed here.

## Ready independent candidate: keep object metadata when evaluating Dang

Dang `ObjectDecl.Eval` already owns the inferred object type and preserves its documentation. It currently discards its object annotations. The engine compensates by rereading and reparsing every module source after declaration, then installing annotations on the resulting types. Even the syntax-cache prototype still clones the entire syntax tree during this extra pass.

The candidate retains the directives alongside documentation in the evaluated object's own Type. The engine then deletes the second source scan. No evaluator, schema, module result or authority is shared across invocations. Dagger's call cache and input identities are unchanged. The metadata pass changes from one additional O(source bytes + AST size) parse/cache-clone traversal to storing a pointer to already-owned annotations; evaluation itself retains its original complexity.

The latest existing wcprof records 10 `dang.objectDirectives` calls totaling 92.0 ms. This is aggregate stage time, not a promise of 92 ms command savings. Cold uncached parsing may gain more; measure before making that claim.

Files:

- `dang-retain-object-directives.patch`: six implementation lines plus targeted tests, against the v2.1.4 library used in the experiment.
- `engine-remove-directive-pass.patch`: removes the engine workaround; independent of syntax-cache prototype but requires the patched Dang dependency.
- `engine-overlay.json`: composes the existing complete-stack overlay with both changes, using the existing build.mod. Does not modify shared source.
- `dang-overlay.json`: focused library tests.
- `candidate-test.log`: targeted tests pass (0.102 s test-package runtime).
- `control-test.log`: original library fails all new metadata tests.

The tests exercise both declaration and full runtime evaluation; retained directive name and argument metadata; distinct Types and directive objects between evaluations; no mutation of the shared Error prelude type; and existing import and positional directive behavior. Full `TestCollections/TestSDKs/dang` and `TestDang/TestDirectives` plus exact greetings listing/edit checks still need to run on a built engine. The engine must not remove the workaround before receiving a released library fix.

Current upstream Dang main has the same omission. Open PR review found no duplicate change in `vito/dang`.

## Current PR ownership and overlap

GitHub's user endpoint confirms `eunomie` is Yves Brissaud. Read-only PR and source review used current public heads, not titles alone.

| Work | Current head | Actual scope | Consequence |
| --- | --- | --- | --- |
| [Go SDK #35](https://github.com/dagger/go-sdk/pull/35), Yves | `289425875b3e2322671b4993d00c1fe63a458a0a` | Opt-in build-only runtime; generation moves out of engine. Runtime still compiles committed source. | Do not claim it eliminates schema-discovery compilation. |
| [Go SDK #36](https://github.com/dagger/go-sdk/pull/36), Solomon | `4dfd447d58344835a0d4692ec0c8e5683c18bd6f` | Generated static Dang ModuleEntrypoint plus dispatch binary in call(). | This owns the large Go types-without-compilation direction; avoid a second portable schema format. |
| [Java SDK #19](https://github.com/dagger/java-sdk/pull/19), Yves | `12a2682d2976c4eb59f8d6c6a501c446ce54a499` | Static Dang TypeDefs from annotation processor model; separate runtime dispatch. | Same static-entrypoint direction for Java. |
| [Python SDK #33](https://github.com/dagger/python-sdk/pull/33), Yves | `e39dcd221f672bbb7d24247ccf7ba701420e160a` | Unified clients; shared or generated static entrypoint. Current shared types() calls describeJSON, which runs installed Python code. | Shared entrypoint alone is not zero-runtime discovery. Test the selected entrypoint mode explicitly. |
| [Dagger #14299](https://github.com/dagger/dagger/pull/14299), Yves | `ceff7b91fdc469f49b39dff98f337c3fdf544e07` | Keys calls on declared client targets and Git commit. | Correct invalidation must survive performance work. Description explicitly leaves large fan-out per-call cost unmeasured. |
| [Dagger #14346](https://github.com/dagger/dagger/pull/14346), Yves | `52a803c5a689fc9b20c8fa0044fd02ba9e46e65e` | Serve local clients relative to owning module, preserving boundaries. | Describes a host-tree snapshot each call. Benchmark this on large trees; never remove it without equivalent freshness and authority. |
| [TypeScript SDK #63](https://github.com/dagger/typescript-sdk/pull/63), Solomon | `46ea4ae0de4514ce62a0c233c66d6943c6fa9822` | Collections support; only non-dependency open TS SDK PR in the current listing. | No matching startup optimization in that open list. |

## Structural next steps, not implemented claims

- Keep the common `ModuleEntrypoint.types`/`call` contract; exercise authors' static-entrypoint migrations instead of implementing a parallel scanner. The builtin greetings-api Go runtime has not automatically migrated merely because this engine interface exists.
- Distinguish source compilation from runtime execution. Prebuilt SDKs remove fixed SDK builds; static entrypoints can remove user-runtime starts for metadata; ordinary check configuration can still need `backend/go-test-base`, so static types alone do not remove every build.
- For TypeScript, warm compiler caches still leave fresh Node startup, loader-worker coordination and SDK evaluation. Simply lazily importing greetings' own source would target only about 4 ms in the earlier isolated diagnostic, so it is not the next large lever.
- The Dang directive fix remains useful as SDK entrypoints become Dang: it removes duplicated work at the producer, preserves existing cache semantics and needs no retained-result cache.
- Preserve real command and edit validation. Small library timings or overlapping process durations cannot demonstrate the 500 ms user loop.
