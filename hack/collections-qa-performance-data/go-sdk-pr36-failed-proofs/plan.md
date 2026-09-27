# Go SDK #36 backend migration proof

This is a bounded correctness experiment, not a performance series. It uses the ordinary frozen ec6 engine, d685 CLI, existing image/init and retained task-owned engine volume. Cloud is disabled through the reviewed lifecycle environment. A new owned engine container is removed after the proof; the original engine stays stopped and unchanged.

The input is a verified copy of the public greetings fixture. Both variants receive the same authored session cache pragmas and JSON transport probe. Only the candidate changes its Go package to an importable package and invokes the exact public Go SDK PR #36 commit plus the already validated JSON contract adapter. No metadata is hand-generated. Generation uses the normal `dagger -y generate dagger-go-sdk/generate` command, with workspace SDK scopes temporarily limited to backend and only the SDK declared in the temporary module catalog. This prevents premature loading of the target while its legacy generated file and newly importable authored package differ; target introspection still uses the real dependency schema. The full workspace configuration is restored after every generation. The original greetings dependency module is not migrated.

The exact cap is 16 local CLI calls:

1. Four initial calls: normal generation then metadata plus actual JSON probe, for each variant.
2. Two ordinary full expanded check listings, requiring the same ordered14 rows.
3. Two metadata observations after adding an authored API method without generation. Record stale graph, fresh graph or error; do not assume the existing TOML baseline regenerates automatically.
4. Four calls: normal regeneration then metadata plus actual new-method dispatch for each variant.
5. Four real selected-check calls: add an application test requiring a live HTTP service and an intentional failure, then edit it into a passing strict HTTP test, for each variant. No `--generated=false` override and no skip path.

Each selected check must report the exact artifact identity and exactly one passed or failed check, as appropriate. Empty selection cannot pass the proof.

The probe preserves a core Directory receiver, Unicode/string/list/null arguments and an integer above2^53. Generated declarations must retain every explicit session cache policy. API names must match after initial generation and include the added method after regeneration.

Four generation calls have300-second limits; other ordinary calls have120-second limits, and the four actual HTTP test calls have300-second limits. Each attempt is recorded before launch and consumes the cap, including failures. A failed migration/validation stops the proof. There is no hidden retry or fallback to old SDK-generated metadata.

The workflow records private raw CLI output and small numeric outcomes separately. Original fixture hashes are verified unchanged. Both private trial copies retain generated migration/API artifacts for review; their full workspace configuration is restored and the temporary application test is removed. The lifecycle evidence is a sibling `results-v2-engine` directory with the helper's existing strict parent check.

The first proof stopped after3 attempts: control generation and JSON/core-object dispatch passed, then candidate generation rejected an absolute local SDK reference before codegen. Its source/results/restoration remain unchanged. The corrected proof replays the same16-call gate from fresh copies. During candidate generation only, the exact validated SDK files are copied into `.sdk36-input` and referenced relatively. The copy is removed on success or failure before API/listing/application discovery; its additional Go modules never enter those later checks. Generated changes are checked against backend SDK-owned paths plus separately recorded ordinary `dagger.lock` resolver metadata, and authored source outside those paths must remain unchanged. The replay adds at most16 local calls, making at most19 across both proofs.
