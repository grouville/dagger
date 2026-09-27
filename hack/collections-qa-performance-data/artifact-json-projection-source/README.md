# Direct artifact JSON projection (source-only prototype)

`readListedArtifacts` and `readListedDimensionItems` currently execute the entire artifact selection to obtain its ID, then issue a second query that appends `__itemsJSON` through `node(id:)`. The prototype appends the same leaf directly to the existing selection. Catalog loading and its filters remain ancestors of enumeration in one GraphQL expression; no collection function starts before its own catalog resolver returns.

The supported SDK offers `Client.QueryBuilder` and object `WithGraphQLQuery`, but no getter for an object's existing query. The smallest seam is a hand-written **internal** `Artifacts.XXX_ItemsJSON` method. It encapsulates the hidden field instead of exposing a selector getter, changing generator templates, using reflection, or reconstructing arbitrary selection graphs in the CLI. It creates a fresh child selection before adding arguments, so the original receiver's query is retained unchanged. The `XXX_` name is explicitly internal, matching existing SDK internal naming; it is not a new public engine/module field.

A nil dimension is omitted; a non-nil empty string is still sent. `absolute` and `typeAssertion` keep their current explicit boolean values. The same JSON decode preserves ordered rows, descriptions and keys. The SDK selection's original GraphQL client executes the leaf, preserving its session binding. The old helper's client parameter remains temporarily unused to avoid a broad call-site rewrite; normal callers already supply that same client.

This removes only the avoidable artifact-ID materialization. An object-valued argument such as `WithArtifacts(otherSelection)` still needs its own ID marshalling and can perform a prerequisite request. The tests explicitly retain that case; this is not a claim that every arbitrary SDK graph executes in one HTTP request.

Errors return without a retry. Cancellation flows through the existing query builder/client and joins the blocked request. Logical producer/catalog errors and selection ordering remain; an expansion error's raw GraphQL response path naturally includes the composed ancestors rather than a separate `node` root. No query authority, cache policy, global alias resolution or evaluated receiver reuse changes.

## Prepared gates

All gates are source-only so far; no compilation or engine calls have been run.

- Actual SDK query parsing verifies one request with retained workspace ID, include/filter/command ancestry, leaf booleans, explicit escaped or empty dimension, and full returned row order.
- A second read of the original selection verifies projection did not mutate its query.
- Another Artifacts argument still materializes separately before the final composed request.
- Two distinct fake clients verify projection stays on the selection's client and never switches authority to an unrelated supplied client.
- Catalog/expansion errors, malformed JSON, and blocked-request cancellation retain failure and join behavior, without retries.
- Existing Go/TypeScript/Dang global dimension-alias and filtered-listing tests run against the composed response shape. The existing fake server now derives that response shape from the real request AST rather than assuming `node.items`.
- An old-source negative run must fail the one-request assertion while using the same independent response oracle.

The previously measured catalog-to-expansion handoff was 38.7/43.1 ms in two separate profiles. It includes first-query completion and the CLI/second-query boundary, so it is only an opportunity bound. No latency saving is established for this prototype. A later matched CLI-only experiment can reuse the same retained engine; it does not need an engine rebuild.
