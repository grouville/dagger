Independent source review of cli-typedef-json-v1

No material source blocker found in the prepared metadata projection. This is a response-assembly optimization for the general CLI call/help path; it does not change selected-check dispatch and cannot explain the selected-check startup profile.

The new resolver selects the existing currentTypeDefs resolver with the same returnAllTypes, hideCore and schema view, and both root fields carry CurrentSchemaInput. The canonical typedef closure, schema ownership, entrypoint projection and module defaults are therefore still resolved by existing code. The final JSON scalar introduces no process-global cache or cross-session TTL. The CLI still performs its existing type-name linking after decoding.

The direct projection correctly handles the two nontrivial metadata adapters currently present: typeDefAsObject produces a collection's public get/subset/keys/list/batch surface, while functionReturnType chooses authored legacy check return types using the current view. The other selected field accessors in module_typedef_canonical.go currently return stored members directly. FunctionArg.defaultValue remains core.JSON, whose MarshalJSON preserves the old GraphQL JSON scalar string representation; it must not be changed to raw JSON bytes. Nil lists are normalized to arrays where the old GraphQL list contract yields arrays; constructors and nonmatching type variants remain null.

The introspection root-field classification includes the new scalar endpoint. core.AroundFunc therefore returns before logResult or call-payload publication for this metadata request, avoiding a new large metadata-value log. Its payload contains the same fields as typedefs.graphql, including authored defaults and default paths; it does not add source maps, environment values, secret values or IDs. Retain that suppression and add a regression test if this becomes production code.

Compatibility fallback is narrow: one exact missing-field GraphQL validation error with no resolver path (and only HTTP400/422 for HTTPError) retries the old query. Authentication, transport, malformed JSON and ordinary resolver errors propagate. Supported engines make one request. This is preferable to retrying all errors and hiding real failures.

Tests/source checks worth completing before an upstream claim

- Existing engine parity tests compare against the authoritative old query for modern/legacy core views and a synthetic collection/check/default fixture. That is a meaningful oracle, not a projection-only test.
- Add absent hideCore vs explicit false and returnAllTypes=false endpoint parity. CLI uses returnAllTypes=true, so the latter is endpoint correctness rather than a claimed CLI performance scenario.
- Cover numeric/boolean/null/array/object JSON defaults, not only a string default. Include optional/list/interface/input references and zero-length arrays.
- Exercise two live attached module schemas with identical type names but different function sets/defaults, proving CurrentSchemaInput prevents stale JSON reuse. Also exercise entrypoint shadowing and canonical constructor linking with a real module.
- Validate collection get/subset/batch execution and help through the new CLI, since equal metadata documents alone do not execute their type-linking consumers.
- Keep the original query contract and projection in sync: the manually copied JSON shape is a maintenance obligation. Parity tests should continue reading typedefs.graphql from the repository rather than freezing a second expected document.

These are independent source-review findings; I have not run or claimed the SDK agent's tests. Module loading and initial TypeDef construction remain. The current implementation allocates maps and serializes a JSON string inside the outer GraphQL JSON response, so retained warm/cold end-to-end measurements are still required; the expected gain is fewer DagQL metadata result operations, not elimination of all schema work.
