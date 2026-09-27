Selected-check startup: retained profile evidence

The retained local-only selected-check diagnostic took 1573.4 ms end to end; its native wcprof window spans 1397.8 ms. All 8260 operations start/end inside the CLI interval, with zero open operations and zero drops. This is one instrumented common-span stack sample, not an ordinary comparison or the latest lazy-core measurement.

| Boundary | Duration | Start after CLI invocation |
| --- | ---: | ---: |
| Workspace.artifacts | 459.3 ms | 146.0 ms |
| Artifacts.__evaluationItems | 772.4 ms | 621.2 ms |
| Artifact.value | 20.9 ms | 1393.9 ms |
| GoTests_Batch.run resolver | 0.089 ms | 1414.7 ms |
| Check.sync | 117.6 ms | 1414.8 ms |

These boundaries are nested where applicable; do not sum arbitrary operations. The warm test result does not launch a new test-runner process, so Check.sync is not uncached Go test execution. Batch replacement still reaches the selected check rather than running every test.

The largest explained expansion chain is sequential: Address.container 372.97 ms, then Go.modules 290.58 ms, then GoModule.tests 73.90 ms. Address.container resolves the configured backend:go-test-base before Go collection discovery. It launches three Go SDK runtime processes: module registration 86.08 ms, constructor 78.67 ms, method 94.70 ms. The enclosing constructor/method calls last 90.60 / 105.93 ms. This is the already-known eager contextual-base/default boundary, not missing DagQL value caching. Broad delayed defaults remain unsafe without freezing all ambient workspace/authority inputs; the isolated pure-constructor cache experiment and SDK static entrypoint work are more scoped options.

Go.modules contains Gomod.modules 215.0 ms. That path issues several Workspace.findRoots, Workspace.file and workspaceRootPath operations in sequence, usually 14–18 ms each. The warm discovery agent is auditing root-name discovery and workspace gateway overhead; use the actual frozen module source before proposing a batched or hoisted replacement. An old source checkout is not evidence for the currently executed implementation.

The existing schema preparation timers are small: schema.forkPrepared has 11 calls totaling 1.77 ms; session.schemaBuild has 131 calls totaling 8.47 ms. These measured paths do not justify a new schema cache as the primary intervention. The standalone dagqlServerForModule path has no dedicated timer in this profile, so its unmeasured portion cannot be called zero. A source-only overlay under instrumentation/ adds fixed native wcprof phases for standalone preparation, NewModTree, native SDK trees and static traversal. It is unbuilt and untested, changes no cache behavior and emits no argument/identity metadata.

Workspace.artifacts contains Query.moduleSource 288.53 ms and ModuleSource.asModule 160.47 ms. The earlier module-source phase includes two overlapping Query.git operations of roughly 90 ms, followed by another moduleSource 104 ms. These are module source resolution, not CLI telemetry Git labels. Removing CLI Git metadata does not remove this work. Module readiness/source resolution is a larger confirmed target than millisecond-scale schema forks.

Suggested order: measure/optimize module readiness and workspace/source discovery; avoid constructing the contextual runtime base until it is needed only if the module/API semantics can safely express that; use the four narrow timers solely to bound remaining static preparation. Preserve check-generated policy, explicit-key membership/order, selected batch behavior, current-session ownership and real source edit invalidation. The JSON metadata endpoint is a separate generic api-call optimization.

Exact module source is now verified: Go collections pin 1784ff37eb3dd1aacab7aaff91b1d86e311cc8de; frozen gomod/main.dang SHA256 78af314f6a53098db6327b8f7eb7e287766f896ab2f545007fe79a5ff214ae1c in warm-audit/module-before. The old direct-library snapshot source was not used for this conclusion. This implementation maps each discovered root through a public workspaceRootPath GraphQL method and reads ws.cwd again; the already-prepared module-cwd.patch changes that pure normalization to a local helper with one cwd read. Its earlier independent eight-pair series measured 84 ms median improvement; that is prior evidence on a different retained stack, not a new gain measured here. Current frozen selected-check fixture still uses the original source, so the opportunity remains visible in this profile.

There are also existing scale terms in that exact module: ownFiles uses an insertion-sort reduce with repeated array concatenation (quadratic time/allocation), nestedRoots repeatedly searches markers for each module, and testNames joins files against every search match. Those are real source-level algorithmic terms but the tiny greetings fixture does not establish them as its dominant wall cost. A native stable byte-order sort and a bulk file→matches index would address scale without replacing Dagger content caching; building an immutable map one entry at a time risks another quadratic construction. Preserve Go's ignored paths, nested-module exclusion, stable key order and duplicate test-name behavior. These were already noted by the warm discovery audit; no duplicate patch is proposed here.
