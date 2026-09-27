# Lazy core metadata: source review and validation

The production patch lets a client execute the installed core GraphQL schema without first materializing every SDK-facing core TypeDef. A real metadata consumer still builds the same per-view definitions through CoreMod.viewState. No cache, TTL, authority scope, or generated client format is added.

This is demand elimination for core-only commands, and deferral for a sequence that later loads a module. It does not reduce the cost of constructing the metadata when it is required. Runtime A/B results are being collected separately; no full-flow latency improvement is claimed by this validation bundle.

## Semantics and scope

- The ordinary schema fork sets the requested API view, preserves installed core resolvers and legacy hooks, and installs the same result/ID loaders. Per-client schema extensions remain isolated.
- First metadata demand retains the existing view lock, complete metadata construction, per-view lookup maps, and MakeResultUnpruneable retention. Later sessions can load the retained result IDs.
- Snapshot-share preparation still rejects ordinary Fork and TypeDefs. The explicit schema-only persisted decoder is unchanged.
- Core metadata is built from the installed core API, not a workspace module schema. Default conversion reads the installed InputSpec.Default and marshals its typed value. It does not resolve UserDefault.Value, host paths, workspace addresses, secrets, or application source.
- Module SchemaBuilder preparation still keys caller-sensitive reuse by ClientScopeAuthority, session and non-module caller. UserDefault.Value continues resolving under the non-module caller's workspace. The production diff does not alter either path.
- A first metadata consumer may now run under a nested module request. The cache already retains engine-owned core metadata per API view; this patch changes its creation time, not its published ownership. Focused cross-session retention and concurrent-first-demand tests passed. The real module/check/generation matrix remains the runtime gate.

## Telemetry implications

Core introspection roots and reflection types are already excluded from ordinary UI spans and the always-on OTel profiler. The builders used by buildTypeDefs originate at those roots; moving them under a user query should not introduce thousands of ordinary Cloud spans. This is a source-level expectation, not a measured payload claim.

Native opt-in wcprof intentionally records reflection operations. Its coverage currently begins inside serveQuery, after initial client bootstrap. A first TypeDef build moved into the query can therefore make previously missing operations visible and increase recorded query duration, even if the total CLI duration is unchanged. Query-only operation counts before and after are not a valid total-work comparison without accounting for this boundary shift.

## Focused validation

Six new tests plus seven existing top-level schema tests passed normally and under the race detector. The existing goldens were not changed. The eager baseline fails the new schema-only fork witness at its attempted cache-backed metadata construction. A separate bounded metadata-content/retention test also passes on that baseline, establishing that the comparison oracle preserves existing semantics.

The accepted run is validation-v5. Earlier attempts are retained privately: one sandbox cache setup failure and three incorrect test assertions/formatters were corrected after checking baseline behavior. The production patch did not change in response. The public numeric summary records this history; giant struct diffs, raw logs and profiles are intentionally excluded.

## Build identity

Both ordinary engines use source HEAD 21939e4ff95dd2be7c584b883b39c5e75b20d703 and the same frozen experimental stack. Baseline SHA256 is bcadd647cc29e737d342cd4e29c6a55f6e49c4919971a7dd7ff1762471bd3660; lazy SHA256 is 56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12. Neither includes the held span serialization candidate. Shared production source was not modified during preparation or validation.
