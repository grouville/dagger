# Next candidate: eliminate core metadata construction, not only response traversal

Source analysis only. No bypass is implemented or benchmarked.

The bulk response proof still calls `currentTypeDefs`. On first demand its saved profile spends469ms constructing metadata; after one same-process primer this is36ms. The response phase remains material when warm:19,861 operations,2,758 publications and156.8ms of elapsed operation coverage. Therefore response bundling has a measured warm target; a direct core snapshot is a separate cold/bootstrap target.

A starting conservative generic gate is `CurrentServedDeps(ctx).Mods()` containing exactly the concrete installed `*CoreMod`, with the same view as the current server. If any user module, wrapper, entrypoint or extension changes module provenance, use the existing bulk TypeDef path. Also verify the installed server is the expected core view: a one-entry module list alone does not establish that no other code installed schema fields. Do not gate on command text or the `version` function. `CurrentSchemaInput` and `.View(AllVersion)` remain on the endpoint, with no cross-authority cache.

Use the already-installed `dag.SchemaForView(view)` and `core.DagqlToCodegenType` conversion, as `getSchemaJSON` already does. That preserves visible fields, exact GraphQL spellings, argument directives, enum members, descriptions and nullability before translation. Generic schema JSON is not itself the CLI manifest: constructors, fields versus functions, source module provenance, ID input interpretation and canonical list names differ.

To avoid two independently evolving translators, extract a pure core signature plan from the existing `buildCoreTypeDefFunctions`, `resolveArgTypeDef` and `currentQueryTypeDef` logic. Both the existing DagQL materializer and the direct CLI projector must consume the plan. The materializer must retain the exact existing selector sequence and IDs; the CLI path can avoid publishing that intermediate graph. The following rules need shared code or exact parity tests:

- Argument `expectedType` and `ID` directive interpretation: ID scalar inputs may become object inputs, including nested lists. Return-type ID scalars remain scalar refs. See `resolveArgTypeDef`/`resolveIDScalar`.
- Defaults: reuse `introspectionDefaultToJSON` with the installed `InputSpec.Default` instead of treating GraphQL literals as JSON. This matters for enum, null, list and object values.
- Canonical names: preserve final names verbatim; only nested nullable list elements add `?`; outer nullability is a separate flag.
- Core object inclusion: the current builder includes Query and ID-bearing objects/interfaces, skips each `id` function, and treats the rest as functions. Do not simply emit every introspection type.
- Query is rebuilt from the current installed root, including argument defaultPath/ignore directives and field module provenance. HideCore retains the `with` function by explicit existing policy.
- ReturnAllTypes closure normalizes outer optionality, adds nested list/ref definitions and prefers full definitions over stubs. Preserve ordering or compare an explicitly keyed semantic form while leaving public CLI order unchanged.

No fresh filesystem/default-path/credential lookup is needed to form this plan: defaults are already declared typed schema metadata. It must not evaluate `UserDefault.Value`. This is distinct from SDK entrypoint generation PRs and does not make SDK compilation disappear.

The first proof should compare both paths against the unchanged authoritative GraphQL selection across the entire core schema and multiple engine views, with focused ID/list/default fixtures. A test must assert core TypeDef construction remains uninitialized after the direct snapshot. Dynamic module paths must demonstrably fall back; no production enablement before those invariants and ordinary cold/warm module-call benchmarks pass.
