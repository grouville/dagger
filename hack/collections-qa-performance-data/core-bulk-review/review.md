# Core metadata publication review

Reviewed the isolated `core-bulk-publication-v1/prototype.patch` against source HEAD `85b60f7a0a16a27459ef571bc94bcf870c876dcc`. This was an independent source and saved-evidence review; no tests, builds, engine calls, or profiling were run by this reviewer.

**Recommendation: suitable for adoption after the matched runtime gate.** No authority, identity, alias, ownership, or view-scoping defect was found. Keep the change limited to core metadata construction; the earlier indexed user-module namespacing experiment is separate and remains rejected.

## Why the cache and ownership model remains intact

- Both new resolvers use `core.CurrentDagqlServer(ctx)` and `FunctionID.Load(ctx, dag)`, exactly as the single-member resolver does. The current resolver server is preferred over the default session server, which preserves dynamic-schema scope. There is no ambient process-global lookup or bypass of typed ID loading.
- The bulk input is an ordered `dagql.ArrayInput[core.FunctionID]`. DagQL's result-call input conversion walks every member into a result reference (`dagql/call_request_input.go:311`). Function identity and input order therefore remain explicit in the ordinary cache recipe; there is no hand-written digest or shortened cache key.
- The final object recipe changes from nested `__withFunction` calls to one `__withFunctions` call. Its outer identity is intentionally different. The contained Function results retain their existing identities. Zero and single-member core paths preserve the previous recipes.
- Each iteration invokes existing `ObjectTypeDef.WithFunction` or `InterfaceTypeDef.WithFunction`. Those functions clone the receiver's slice before replacement/appending. They preserve first-slot matching by original or normalized name, including ambiguous alias cases, without inventing an index with different precedence.
- The resolver returns a normal result; `ObjectTypeDef.AttachDependencyResults` and the interface equivalent still attach the retained functions and their nested argument/return-type graph. Ordinary core view retention still makes the final TypeDef graph unpruneable. Intermediate growing object publications are no longer needed to retain the final graph.
- Failed ID loading returns an error without publishing a partially constructed result. The originally held receiver is unchanged because each update cloned it. Previously loaded inputs may still acquire normal session references, as on other failing selections; no new cross-session lifetime mechanism is introduced.
- The core view and snapshot-share preparation checks are unchanged. Construction occurs through the same view-specific server. No additional field visibility, collection marker, legacy ID, or CLI projection rule is changed beyond adding the private builder operation alongside the established private builders.

## Evidence and its limits

Saved validation records show the work witness fails on the unchanged consumer for the ten-member object/interface cases and passes for the candidate. Candidate and race runs also pass the schema allowlist, core metadata after session release, currentTypeDefs after session release, and JSON projection parity for v0.21.5 and v1.0.0.

The custom ownership test compares exact child Function engine result IDs, descriptions, argument defaults, held-parent immutability, and child/argument loading after producer-session release while a consumer holds the final result. It does not prove equality of outer object IDs across two different recipes; that equality is not required or expected.

Saved first-construction microbench medians (three samples) are 291.62 -> 238.92 ms, 96.09 -> 82.48 MB/op, and 1,274,981 -> 1,087,964 allocations/op. This is fresh local core metadata construction, excluding installed-schema setup and cache teardown. It is not a claim about complete CLI wall time, warm invocations, or the 500 ms goal.

The loop still invokes F immutable updates that clone and scan growing slices, so local update complexity remains O(F²). The reduction is F-1 intermediate DagQL publications and their repeated attachment/identity work. Do not describe the whole operation as linear.

## Small follow-up before finalization

Add a focused object/interface resolver test using duplicate normalized names and conflicting original names, comparing the final ordered child IDs to sequential selection; include a failing ID after a valid member and confirm the held receiver is unchanged. Existing source reuse already preserves these rules, so this is targeted regression protection rather than a finding of incorrect behavior. The older `typedef-bulk/typedef_bulk_test.go` contains a useful adversarial alias sequence, but that separate implementation and benchmark should not be imported.

Update `core-bulk-publication-v1/README.md`: its opening and closing paragraphs still say no tests or builds have run, while saved validation and matched engine build evidence now exist. Keep the preparation history separate from the final disposition.
