# Dang admission and module readiness: two current-stack profiles

Four local calls passed: primer, profiled unchanged `check -l --all`, primer, profiled unchanged listing. Every output contained the exact fourteen expected checks. The original engine/init and workspace remained unchanged; the temporary engine was removed, the isolated fixture was restored, and the retained volume was preserved. No Cloud calls. The two profiled commands are diagnostic observations, not an A/B performance claim.

The engine was rebuilt from effective `38711` sources with profiling only: seven fixed Dang phases and a canonical module-resolution marker. Binary `6a82b8b3` has its own build stamp `v1.0.0-beta.15+b0fda131`. CLI `d685` and Go module `0b12` are unchanged. Both captures contain 18,143 operations, 15 Dang runtime calls, 9 workspace module loads, no open operations and no dropped events.

## What explains the earlier unmarked constructor prefix

| Go constructor phase | Capture1 | Capture2 |
| --- | ---: | ---: |
| Whole Dang runtime call |86.354ms|42.655ms|
| Obtain dependency-schema File |20.698ms|14.163ms|
| Register nested transport |0.035ms|0.027ms|
| Create nested listener |0.037ms|0.051ms|
| Open schema File |0.627ms|0.645ms|
| Decode schema |11.644ms|8.455ms|
| Clone schema |0.549ms|0.389ms|
| Source mount, including source evaluation |22.744ms|10.293ms|
| Source evaluation alone |13.397ms|9.663ms|
| Invoke, including nested work and flush |29.604ms|8.215ms|

The retained constructor no longer has an unexplained 36ms block: the new phases show schema preparation first, then decode and source evaluation. Values differ between captures, so the old 36ms gap must not be transferred unchanged to this run. File materialization is a small warm cost: all six schema opens total 12.951ms in capture1 (including one 8.621ms outlier), then 5.134ms in capture2. Avoiding that I/O might be useful elsewhere, but this evidence does not support it as the primary warm-discovery target.

Schema preparation is already amortized per dependency builder. In capture2, the first Go call spends 14.163ms obtaining its schema File and the first gomod call spends 11.755ms; the remaining thirteen calls each spend 0.051–0.076ms. All fifteen `Query.__schemaJSONFile` selections are cache hits, totaling 0.343ms. `runtimeImpl.Runtime` creates a cheap wrapper around the existing `mod.Deps`; it does not clone the builder. `SchemaBuilder.lazilyLoadSchema` retains the prepared schema. Removing another runtime wrapper or adding a schema-File cache would therefore address less than 1ms on those thirteen repeated paths.

## Expansion, excluding registration

Capture2's collection expansion lasts 367.089ms. These are interval unions within that expansion, not additive contributions:

| Phase | Count | Inclusive sum | Interval union |
| --- | ---: | ---: | ---: |
| Obtain dependency-schema File |15|26.740ms|26.727ms|
| Decode schema |1|8.455ms|8.455ms|
| Clone schema |15|7.099ms|5.681ms|
| Evaluate source |15|130.458ms|81.286ms|
| Invoke |15|643.932ms|295.592ms|
| Flush telemetry |15|51.881ms|48.970ms|

Only 32.627ms of source-evaluation intervals fall outside every invoke interval. Invoke intervals excluding every active flush interval cover 246.622ms, but this is not exclusive CPU: nested GraphQL requests are recorded under separate request roots. Each invoke exposes its flush as a direct profile child; none has a parent-linked nested runtime descendant. Treating the remaining 283.575ms direct-child-subtracted union as pure authored work would be incorrect.

`RunDir` really does repeat parsing/cloning, fresh prelude/type-scope creation, inference and evaluation on every invocation. The current `runSource` label does not separate those stages and cannot attribute its 81.286ms union entirely to cloning or inference. The actual runtime calls are eight Go calls (constructor, modules, three get and three tests) and seven gomod calls (modules, three workspace-root conversions and three own-files calls). This creates a concrete opportunity to remove avoidable module-call boundaries without retaining evaluated environments; the separate path-normalization helper change already targets the three public conversion calls, but its combined current-stack effect has not been measured here.

The schema-file hit and builder reuse observations rule out repeatedly rebuilding the same schema as the dominant explanation. A next algorithmic experiment must measure the actual retained parser/clone baseline, not the older dependency checkout.

## Module readiness and the catalog barrier

| Relative to catalog start | Capture1 | Capture2 |
| --- | ---: | ---: |
| Go module resolution complete |545.628ms|388.016ms|
| Last module resolution complete (TypeScript SDK) |680.086ms|586.496ms|
| Catalog complete |700.166ms|604.167ms|
| Collection expansion starts |734.516ms|628.124ms|
| Collection expansion complete |1330.757ms|995.213ms|

Go resolves 134.458/198.481ms before the last module, and the catalog/expansion are sequential in both captures. This confirms possible overlap to investigate, not an automatic saving: resolution completion precedes publication, and the existing batch still arbitrates errors, installs modules, and establishes the schema/dimension view after all jobs finish. No scheduling was changed or proven safe by these markers.

## Existing clone optimization is already present

The effective parser overlay is SHA `b0f575ce0e8c7acc803e9aa7ae73e2a4da5d7b55ba21b2d02cdb04a0805258a0`. It already returns primitive/nil reflection values before allocating an addressable temporary. Looking only at the underlying isolated dependency source misses that overlay. Earlier unit/race tests and real-go/gomod microbenchmarks are preserved under `sdk-edit-audit/dang-clone-leaves`; their 14–19% cached-parse improvement is historical and already included in this stack, not a new predicted gain. The old 221MiB clone allocation profile predates that effective change.

A distinct follow-up could copy composite nodes directly into an already owned destination, avoiding temporary struct/interface/pointer boxes while preserving every mutable clone. That remains a separate unmeasured candidate; no dependency or execution-state reuse is proposed here.

## Exact evidence

- Capture1 SHA:`4d80046bcfa5cac7fbe35e95e130a1c79280d583fe62118c4285ae361903d3a0`.
- Capture2 SHA:`f8f2d15174f9a3cd1e6886215b3ac9f140562b591b4ee72343a225a38e0bde62`.
- Diagnostic engine SHA:`6a82b8b305b8415e42cc451e3ec5bd56208ab20eadc87b6a1a8de2a9c6685b4a`.
- Recipe SHA:`123625a674c5b43a0a001b45851cbe2d5008c9e0ca4a47f1c355e968c8ba7464`.

`reduce.py` verifies profile hashes and emits only fixed classes, numeric intervals and explicitly allowlisted public aliases. Raw profiles, operation/client IDs, arbitrary names, private stdout/stderr and container metadata are excluded from publication. The safe allowlist includes the build recipe, phase patch, runtime source, correctness/restoration and numeric evidence.
