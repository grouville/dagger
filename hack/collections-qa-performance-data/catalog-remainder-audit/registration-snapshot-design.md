A per-registration metadata snapshot can remove one source parsing pass from current production `core/sdk/dang/v2/helpers.go` without sharing inferred state or introducing a cache. It is not a further win over the measured experimental helper: that helper already omits `retainDangObjectDirectives`, whereas current production still calls it.

Production registration currently performs these operations inside one mounted immutable module directory:

1. `ensureModuleSelfTypes` → `moduleDeclaredTypeNames`: ReadDir, parse every top-level .dang file, retain public declaration names only. Errors are best-effort and the main object name is seeded regardless.
2. `runSource`: independent Dang declaration/inference or runtime evaluation. It owns its own AST and scope and remains unchanged.
3. `retainDangObjectDirectives`: ReadDir and parse those same files again, then attach each top-level object's raw directives to its inferred constructor type. This includes objects regardless of public visibility.

Minimal design: a local `registrationMetadata` holds ordered public declaration names, ordered `(objectName, directives)` entries and the first deferred read/parse error. Parse source once before self-type installation; collect copied names and raw directive nodes from that newly owned AST. Install namespace placeholders from the names. Invoke the unchanged `runSource`. Only if that succeeds, propagate the deferred metadata error or attach directives using the returned environment. The snapshot lives inside this one `Mount` callback and is never published, cached, inferred or shared across clients. The separate evaluation AST remains owned by Dang.

Preserve the original fallback/error boundaries: seed the main name, skip malformed files for name discovery, retain deterministic ReadDir/form order and deduplication, and let runSource's rendered diagnostic take precedence. Do not evaluate directive arguments early; attaching the same raw AST form after inference preserves lexical-scope handling. Do not filter private object directives simply because declaration names include public types only. A mounted immutable Directory is the input contract; this is not a host filename/mtime cache. Ordinary runtime calls with `registerTypes == false` must do no metadata read at all.

For N source bytes, this removes one O(N) parse and one directory listing per registration; it temporarily retains the directive AST nodes between the two existing phases. It does not reduce inference complexity, skip bodies where previously evaluated, or reuse a schema beyond its authority. For the measured38711 helper, removing its remaining names-only parse would instead require an owned parsed-directory input that DeclareDir can consume, or a narrow parser-owned declaration-name API. Do not quietly combine those larger changes with the production-only snapshot.

Decisive focused tests:

- Count parser invocations with an internal injected parser: each selected top-level .dang file once during metadata collection, once only in the unchanged runner; baseline's second metadata pass must fail the count witness. Directory entries and results remain ordered.
- Public objects/interfaces/enums/scalars, private and nested declarations, duplicate names, namespace aliases, existing schema entries and unconditional main-type seed produce identical placeholders.
- Top-level object directives with arguments referencing file-local declarations reach the same inferred constructor and evaluate identically after runSource. Private object directives retain their existing behavior.
- A parse/read failure preserves seeded names but is deferred. A runSource error wins; when the runner succeeds, the same first metadata error is returned. Do not invent successful source parses to conceal errors.
- Two registrations with different source snapshots, namespace/configuration or caller schemas cannot share node pointers/state; run them concurrently under race checking. An ordinary runtime call invokes no metadata parser.

Before a production speed claim, measure the current production two-pass helper against this snapshot on the same dependency revision. The frozen38711 profile is not that baseline. The latest diagnostic measures12 remaining selfTypes calls at79.31ms union; that is a bound on the separate future names-pass optimization, not evidence the snapshot can save79ms on38711.
