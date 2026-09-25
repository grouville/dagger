# Collections performance branch: main rebase

On 2026-09-25, `perf/collections-discovery` was rebased from
`c2d178e06ec39976ce03ed2744e544500d8c7841` onto
`origin/main` at `d8f1f0d6d2b7bec54c4841bcc0e6da3e031fb1bd`.
All 182 commits were replayed. The replay ends at
`a334cb6203d5ac7e3727e77901a8c02f57d35a72`; subsequent commits repair the
generated API files and test snapshots, and record this validation.
The local recovery branch is `backup/perf-collections-before-main-c2d178e06e`.

## Telemetry baseline

The branch now includes [#14303](https://github.com/dagger/dagger/pull/14303),
which splits Cloud publishing from client presentation, and
[#14341](https://github.com/dagger/dagger/pull/14341), which probes and caches
Cloud reachability before the engine takes over publishing.

The conflict in `CloudEngineClient` retains main's
`scaleOutTelemetryParams` routing and the collections workspace, environment,
extra-module and test-runner configuration. The CLI telemetry setup matches
the new main implementation.

This is not a measured removal of all shutdown latency. The engine still
flushes session Cloud telemetry during `serveShutdown`, with a shared bounded
shutdown budget. The earlier 312 ms export wait and approximately 2.29 s full
listing median describe the pre-split build. They must be remeasured on this
base before choosing another optimization. The 500 ms objective remains open.

## Rebase repairs

* Regenerated GraphQL documentation and Rust bindings from the combined
  schema, retaining both collections and main's new `Container.withGPU` API.
* Refreshed the base-schema snapshot for the collections shell API's existing
  deprecation and optional overrides; no resolver behavior was changed.
* Kept main's nested failing-test fixture and assertions in the two conflicted
  TUI goldens. The check command still must exit unsuccessfully. The direct
  call now reads the collections `Check.pass` field and must print `false`;
  both cases verify the failed leaf, linked continuation and test counts.

## Validation

Fresh CLI and engine binaries were built from the rebased source. An isolated
engine and new state volume were used for integration tests. Its base image
supplies the existing SDK payloads: these were not all rebuilt, and the Dang
and TypeScript performance prototypes were not enabled. This is correctness
validation, not a comparable performance run.

* Focused analytics, engine telemetry, client, server and core tests passed,
  including Cloud publishing/fallback, stream ownership, scale-out routing,
  bounded flush, and artifact schema isolation.
* Focused CLI Cloud and telemetry tests passed. The initial invocation used
  an outdated CLI from `PATH`; rerunning with the rebuilt CLI corrected that
  harness mismatch.
* Ten artifact/collection integration cases passed, including edits,
  discovery-session expiry, module boundaries, check caching, batch
  replacement, selection, enum keys and schema-only listings.
* GPU and nesting version gates, workspace address views, and the base schema
  snapshot passed. Both TUI cases passed with snapshot update disabled.
* The normal Rust binding generation/fix workflow compiled successfully.

This was targeted validation, not the entire integration suite or a full
Cloud telemetry end-to-end run. Commands and a compact result summary are
archived in [the validation record](collections-qa-performance-data/rebase-main/validation.txt).
Historical benchmark evidence is left unchanged.
