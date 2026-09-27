# CLI metadata response candidate

The original metadata selection performs about20,000 field operations even after a same-process primer. In the warm diagnostic, forming currentTypeDefs took36.0ms; the following response operations covered156.8ms and published2,758 results. The actual version query took0.36ms. On first demand, TypeDef construction instead took469.4ms and response traversal323.6ms. These are separate local profiled observations, not ordinary A/B performance gains.

The candidate keeps the same schema-scoped metadata and emits the CLI projection in one JSON scalar. It preserves collection projection, legacy check return types, typed JSON defaults and canonical names. A new CLI falls back only when the engine rejects this exact missing field. Matched runtime performance and real module command correctness are still pending.

Testing caught and fixed a real view-context bug: the JSON root field must declare AllVersion, because the legacy return-type adapter reads the current call view. Fixture optional-argument and typed-root accessor errors were also corrected; earlier failing logs remain private and are not rewritten. Final validation/build manifests are added only after completion.
