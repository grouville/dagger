# Most discovery latency is inside API requests

The latest selected full-listing result remains **53.58 → 46.72 seconds** from the span-index comparison. A new diagnostic completes in **45.54 seconds**, returns the same 4,398 rows and exits successfully. It adds measurement hooks, not a performance fix; its time must not replace the unprofiled result.

The earlier `dang.invoke` interval included function evaluation, synchronous API requests, telemetry flushing and JSON encoding. New wcprof operations separate those activities while retaining the original HTTP/GraphQL client and engine request path. Every one of the 7,820 API operations is verified to be parented under its function evaluation.

## What holds up the main query

The main query lasts 43.00 seconds. Package discovery completes at 17.86 seconds and collection expansion at 32.70 seconds; reading and publishing metadata occupies about another 10.3 seconds. Critical-path attribution is rooted at that query, operation 7068:

| On-path work | Time |
| --- | ---: |
| Synchronous API processing from Dang | 29.42 s |
| Dimension-key element materialization | 4.14 s |
| Cache publication | 2.50 s |
| Artifact element materialization | 2.50 s |
| Function evaluation outside recorded API calls | 0.59 s |
| Telemetry flushing | 6.77 ms |
| Encoding module results | 3.16 ms |

The API intervals include client encoding/decoding, transport and backend processing. They are not network delay alone. The function-evaluation row is elapsed critical-path time, not interpreter CPU. The element labels name synthetic indexed reads, not repeated execution of the original list resolver.

Telemetry flushing sums to 537.75 seconds across 963 concurrent invocations, but contributes only 6.77 ms on this query's path. That distinction explains why reducing flush work or allocations can save substantial aggregate work without making listing much faster. All wcprof chunks total 582,293 events, with none dropped or left open.

## A concrete engine cost before cache lookup

The CPU profile identifies repeated Git-client declaration lookup while forming module-function cache keys. `ModuleFunction.declaredGitClientsDigest` visits the configuration governing the module even when the function result is already cached. Across the complete CPU capture, `workspace.DeclaredGitClients` accounts for 13.65 sampled CPU-seconds, including **10.38 CPU-seconds in `ParseConfigAt`**. Restricting attribution to nested API handler stacks accounts for 11.76 CPU-seconds in declaration lookup and 8.26 in parsing; these are subsets, not additional costs.

`ParseConfigAt` decodes the configuration with `toml.Unmarshal`, then `CheckConfigFields` parses the same bytes again with `toml.LoadBytes`. The latter tree construction alone accounts for 2.63 sampled CPU-seconds. The first experiment should share a parsed document between decoding and field validation. The pinned library's `Unmarshal` already delegates decoding to `Tree.Unmarshal`, so this can preserve the existing decoder instead of changing libraries or weakening validation.

Live configuration reads matter: local modules read the caller's current files, and unreadable declarations deliberately prevent cache reuse. An optimization must preserve fresh reads, nearest-config selection, errors, warnings, SDK-scope reconciliation and cache-key contents. No declaration lookup is skipped, and no configuration cache has been introduced.

The synchronous `http.Transport.roundTrip` stack accounts for only 0.14 sampled CPU-seconds. This excludes separate transport goroutines and is not a bound on all network time; it does not justify replacing the transport before investigating the measured engine work.

## Capture and checks

The capture uses a warm owned engine, a fresh CLI and source edit, the same Go module and normal telemetry/GC. Scope-map laziness, circular queues, resource reuse and flush coalescing stay off. Span indexing stays on. CPU windows cover 50.04 seconds, including roughly 4.5 seconds after command completion; their 235.90 sampled CPU-seconds include concurrent and maintenance work. Host I/O stalls reach 7.17%, so this remains diagnostic evidence.

The new attribution test preserves request/response objects, caller context, errors and cancellation, and verifies API operations' parents. The shared SDK and v2 SDK tests pass; shared SDK race checks pass. The owned engine restarts gracefully on the same volume, and all six retained Rust histories reuse every compiler action before and after. The engine now runs `0ffed897…`; profiling is off, no session remains active and all unselected modes are off.

[The evidence archive](experiments/dang-invocation-phases/) contains the hooks, tests, exact engine overlays, raw profile chunks, CPU windows, source lines, derivations and restored state. It also retains the relevant configuration source for the next experiment. No PR is opened.
