# Defer a custom Go base through an explicit Address input

This experiment separates a small generic engine fix from an opt-in module API. Source is isolated here; no shared checkout change or engine-runtime result is claimed. `validation-v1` is retained: the original source fails on nonexistent `Address.address` as expected; the candidate reached the bound values, then the first test incorrectly requested a recipe digest from a handle-form ID. This test-only assertion has been changed to encoded handle equality; the corrected normal/race/parser gates pass in `validation-v2`.

## Engine: Address is already the requested value

`UserDefault.Value` first resolves a user setting through the non-module parent's schema and `Workspace.resolve`. It then normally calls a typed loader such as `Address.container`. For an argument whose type is itself `Address`, it incorrectly tries `Address.address`, which does not exist. The patch returns that already-resolved Address result, then uses the same existing ID selection as every other object argument.

There is no global cache, deferred Container shell, new cache policy or ad-hoc serialized plan. Lists use the same per-element path. The existing Address dependency/persistence implementation retains its originating Workspace; selecting its target later still applies the original owner's resource routing and the consumer's runtime authority. Existing Container arguments remain eager and retain their error timing. An Address intentionally postpones target/type errors until the module calls a typed loader; an unused address may never select its target.

The focused tests call real `UserDefault.Value`, `CallInput` and `DagqlID`. A small fixture schema makes eager target selection observable without an engine, image or filesystem mount. They exercise two caller-bound workspaces with the same URI, distinct Address IDs, ID round-trip, eventual use from a different active workspace, unchanged eager Container errors, empty/multiple Address lists and repeated successful per-call target selection. They do not substitute for the actual module caching/runtime witness.

## Module: preserve the existing base, offer a lazy address

On `dagger/go@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`, the optional `baseAddress: Address` constructor argument is appended after `mountPath` so all existing positional arguments keep their positions. `base: Container` stays supported; specifying both reports an ambiguity. `version` is ignored with either custom base, and warnings name the setting responsible.

The Address flows as configuration from Go through GoModules into the private GoModule input. Only `GoModule.base(ws)` calls `.container`. Module/test discovery uses Workspace reads and never needs that method; version introspection checks whether either custom input exists without selecting a target. Execution keeps `withoutEntrypoint`, `gomod.withGoCaches`, warnings/workdir/GOFLAGS and the produced Container—including its services, files and environment.

The workspace setting migration is explicit:

```toml
[modules.go.settings]
baseAddress = "dag://backend/go-test-base"
```

Remove the old `base` setting when opting in. Workspace setting names match the authored argument case-insensitively; they currently do not normalize hyphens, so use `baseAddress` here (the CLI flag spelling is separate). Typed Address is deliberate: storing a String and resolving it from an arbitrary later `ws` argument would change which workspace owns the configured address. Calling `Query.address` would also lose `dag://` workspace resolution in the modern API.

## Prepared correctness gates

The module's existing GoDev suite gains two checks plus two non-check producer fixtures:

- A producer that always fails proves listing module/test keys does not consume the base; asking for its Container must surface that exact error. Also checks version warnings and conflicting settings.
- A successful producer retains the existing strict custom-base fixture (required env + file), adds a workspace-derived marker file and a real HTTP service carrying the marker, and runs existing test/generate paths. Missing environment/file/service cannot silently pass. The marker file can be edited/restored in a task-owned copy to prove source invalidation.

Actual module gates are not yet run. Before performance measurements, also retain one GoModule handle in one session and call `base` repeatedly with the same Workspace. A nested per-call/NEVER target does not automatically imply the outer module function re-executes on every cache hit. We must characterize that ordinary function-cache boundary rather than claim a new blanket NEVER guarantee or disable caching broadly. Source preparation for this witness is owned independently by the cold-audit agent.

## Matched greetings fixture

For a later fair performance trial, both variants must use the same local module layout, not compare a remote control with a local candidate:

1. Put only `go.dang` and `dagger-module.toml` at the same `.dagger/perf-go` path in an isolated greetings copy.
2. Keep `gomod` as the ordinary pinned dependency `github.com/dagger/go/gomod@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. Do not copy its helper Go module into the application tree.
3. Control has original go.dang and `base`; candidate has patched go.dang and `baseAddress`. Keep backend/service implementation and all SDK pins identical.
4. Verify exact fourteen check rows and selected custom-base HTTP check success, missing/incorrect service negative control, source edit→check/generate and restore. Store normal full-exit timing separately from diagnostic wcprof.

The separately pushed private-path-normalization module commit is not part of this comparison. No current-stack saving is promised. The observed configured-base span (roughly 200–223 ms plus overlapping repeats) includes work with dependencies and is a motivation, not a forecast or an amount to add to another optimization.

## Why this is smaller than the previous generic lazy-default prototype

The older isolated `@lazyDefault` prototype created a Container proxy, froze explicit arguments and carried session ownership, but remained blocked on ambient workspace observations, persistence/restart and identity equivalence. It was not upstream-enabled. This change exposes a real existing Address API instead: the module author chooses the force point, the user opts in, and all Container behavior remains the original producer result. It still shifts required producer work into execution; removing listing work is not a promise of the same improvement when actually running a check.

## Completed offline validation

At source HEAD 2088d5ef, the original engine source fails the new direct/default-list witnesses because `Address.address` does not exist. The candidate passes all three Address tests and the existing `TestUserDefaultWithoutDotEnv` group, ordinarily and with Go race instrumentation. The Go module, GoDev QA additions and retained-consumer fixture all parse as Dang. Parsing is not type inference or engine runtime validation; service binding, real source edits and outer method-cache behavior remain the next runtime gates.

No engine, image, Cloud or timing benchmark was invoked by this validation. The 26.3/48.1 second validation durations include compilation and are not user-command latency. The initial candidate test-only handle-ID assertion failure is retained privately in `validation-v1`; production source was unchanged by its correction.
