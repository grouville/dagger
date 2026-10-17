# Reuse preparation during Go collection listing

The full Go listing remains slow. Removing 800 nested SDK invocations for package ownership does not establish a complete-command improvement: one diagnostic pair takes 190.31 seconds before and 203.27 seconds after. Both succeed and return the same 4,398 rows. Cumulative engine CPU falls from 423.62 to 358.35 seconds and allocations from 55.13 to 50.15 GB, but those reductions are not a latency win. The temporary duplicated module helper remains unselected.

The next experiment reuses prepared Dang declarations. It leaves the selected Go module unchanged. Every call still receives its current client, cancellation context, parent object and arguments, and executes its normal Dagger queries. No workspace, function result or compiled test result is cached by this experiment.

The diagnostic gate accepts only directories consisting of object declarations, without static initializers, nested types or explicit imports. Unsupported initialization follows the existing per-invocation path. Entries are keyed by the module source ID, runtime schema file ID and current source mount path, and the in-memory cache holds at most 32 entries. Including the mount path preserves source locations; it may also limit reuse. A stateless client stored in the declarations resolves the actual GraphQL client from each invocation's context.

Focused race tests pass for 32 concurrent clients, each creating three independent receivers and arguments. They also cover missing clients, source/schema changes, initialization effects and the gate's accepted/rejected source forms. Both actual Go and Gomod sources pass the gate. This does not prove that arbitrary interpreter state is immutable; the mode is an opt-in diagnostic, not a production selection or an upstream PR.

Two integration failures changed the prototype. The first assumed every source/schema ID had a recipe digest, but handle-form IDs panic on that operation. The key now uses the supported ID encoding, with a regression test. That panic caused an unclean shutdown; the engine deliberately cleared its query cache on recovery. All six Rust benchmark histories were rebuilt and again pass strict reuse. Timings from the recovered engine need their own baseline and cannot be compared directly with the earlier approximately 100-second runs.

The second failure occurred when serializing a lazy GraphQL object to JSON. Prepared functions retain a stateless client, but JSON marshaling has no invocation context. Functions now bind their newly created values to the current client; the cached declarations retain no live client. A regression marshals values from two invocations and checks their IDs. With unique fixture inputs, both package ownership across added/removed module boundaries and the existing Go test-collection execution check pass. These checks record 314 cache hits across five preparation entries. Temporary fixture changes are restored before timing.

Two clean comparisons in opposite orders complete successfully with identical 4,398 rows:

| Order | Without reuse | With reuse | Allocation without → with |
| --- | ---: | ---: | ---: |
| Control, candidate | 121.29 s | 82.44 s | 75.42 → 42.56 GB |
| Candidate, control | 90.44 s | 84.55 s | 50.57 → 42.89 GB |

These are complete commands, including cleanup. Every arm starts a new CLI and receives a fresh source edit. Telemetry and ordinary garbage collection remain enabled; the separate known-ID change is off. The selected Go module is unchanged. The first candidate records 1,759 reuse hits and three preparation misses; the first control records about 20 ms of snapshot-metadata GC during its command. Its 184 Go memory collections are separate from that snapshot collector.

Both orders improve CPU work, allocation and latency, but the controls vary considerably. The observed full-command gain is 6–39 seconds; two pairs do not establish a stable 32% improvement. The candidate's 82–85 seconds is still far from a fast listing. The prototype remains unselected pending broader interpreter review and stronger timing evidence.

The completed diagnostic takes 87.36 seconds, succeeds with 4,398 rows and records 555,946 wcprof events with none dropped or left open. Across 1,762 invocations, parsing, inference and declaration evaluation run only three times. Their summed recorded durations are about 24, 23 and 3 ms respectively. `dang.invoke` still includes awaited API work; its concurrent durations are not interpreter CPU time.

The CPU and allocation profiles identify a concrete next target. Every `FlushSessionTelemetry` call flushes the session's shared trace/log providers and fans out over every client metric runtime. The Dang runtime calls it after each invocation. With many concurrent clients, this multiplies provider work. Metric reader flushing accounts for about 12% of one five-second CPU window; its containing reader operations overlap that percentage. A coalescing flush must preserve a barrier for every caller's already-emitted telemetry, including calls that arrive during another flush, errors and cancellation. This is a performance experiment to implement next, not a demonstrated fix. No telemetry is disabled.

A separate, independently disabled experiment marks converted input object IDs as already known. The converter currently builds a lazy `node(id)` handle but leaves `KnownID` empty, so serializing the handle can query for the ID it already has. A focused regression verifies JSON serialization without a client or extra request. Fresh-input ownership and real test execution checks pass. One complete listing pair takes 89.90 seconds without it and 91.00 seconds with it, returning identical rows; it does not establish a full-command gain. It remains unselected. Interface/namespacing behavior still needs broader validation before proposing it independently.

The [source and evidence archive](experiments/go-dang-reusable-declarations/) retains complete attempts, including failures, and the source manifest.
