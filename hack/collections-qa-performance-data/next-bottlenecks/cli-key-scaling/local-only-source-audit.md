# Local-only diagnostic mode: source audit

This audit permits an explicitly labelled diagnostic without Dagger Cloud, OTLP export, or analytics. It does not make its timings comparable to normal Cloud-enabled CLI exit times, and it does not claim that arbitrary module functions never access the network.

## Required process environment

Before starting each fresh CLI process:

- Remove `DAGGER_CLOUD_TOKEN`, `DAGGER_CLOUD_URL`, `DAGGER_CLOUD_AUTH_URL`, `DAGGER_CONFIG`, and inherited `OTEL_*` variables.
- Point `XDG_CONFIG_HOME` to a newly created, empty, task-private directory (mode 0700). Do not alter or copy the user's existing configuration or credentials.
- Set `DO_NOT_TRACK=1` and `DAGGER_NO_UPDATE_CHECK=1`.
- Remove `DAGGER_SESSION_*`, `TRACEPARENT`, `TRACESTATE`, and `BAGGAGE` to avoid inheriting an existing session or trace.
- Remove `_EXPERIMENTAL_DAGGER_CACHE_CONFIG`, `_EXPERIMENTAL_DAGGER_CACHE_IMPORT_CONFIG`, `_EXPERIMENTAL_DAGGER_CACHE_EXPORT_CONFIG`, `_EXPERIMENTAL_DAGGER_CHECKS_SCALE_OUT`, and inherited `DAGGER_CLOUD_*` settings, including the old cache-token setting.
- Select the verified local engine explicitly with `--engine container://dagger-engine.collections-disk-abba-2`.

No endpoint is redirected. No credentials are changed. The local frontend and local engine telemetry still operate normally.

## Source evidence

1. `internal/cloud/auth/auth.go:31` derives its credential and organization paths directly from `xdg.ConfigHome`. `Token` at line 233 first reads that credential file and returns immediately on a missing file; no refresh occurs. `GetCloudAuth` at line 485 returns `nil, nil` when both the environment token and that file are absent. It does not search the original home directory or system XDG configuration directories.
2. `engine/telemetry/cloud.go:26` returns unconfigured exporters when `GetCloudAuth` returns nil. `internal/cmd/dagger/engine.go:409` then retains the frontend exporters but leaves Cloud indexes unset. `finalizeEngineParams` at line 192 enables `EngineCloudTelemetry` only when those Cloud indexes are configured.
3. `engine/client/client.go:1778` publishes the engine Cloud-telemetry request only when both its flag and `CloudAuth` are present. `engine/server/session_cloud_telemetry.go:38` independently requires that publisher request and a supplied token before checking Cloud reachability or creating exporters. There is no fallback to engine ambient credentials for this session. Scale-out telemetry also returns before enabling a Cloud publisher when the parent session does not publish.
4. The pinned `github.com/dagger/otel-go` implementation (`init.go`, `ConfiguredSpanExporter`, `ConfiguredLogExporter`, `ConfiguredMetricExporter`) creates no auto-detected exporters without their OTLP endpoint environment variables. It does not silently select localhost or a default remote receiver.
5. `analytics/analytics.go:114` returns a no-op tracker with `DO_NOT_TRACK=1`. The client also sends that preference in its metadata (`engine/client/client.go:1766`), and `engine/server/session.go:949` disables the session tracker when either the client or engine opts out. Git labels may still be collected locally; the disabled trackers do not upload them.
6. `internal/cmd/dagger/main.go:390` skips the update-check goroutine with `DAGGER_NO_UPDATE_CHECK=1`. At line 426, a missing credential file does not trigger login. `internal/cmd/dagger/llmconfig/config.go:59` otherwise allows `DAGGER_CONFIG` to override XDG isolation; removing it and using empty config makes `enabledOAuthProviders` empty, so `startOAuthTokenRefresher` starts no goroutine.

## Existing engine configuration

Read-only Docker inspection checked these exact previously verified task-owned containers, without printing or copying any credential values:

- `dagger-engine.collections-disk-abba-1`, ID `6c1c8136c625198bc84bdcd4f1c5f203ed99fd6d1aa6282e0479a81723c2e584`.
- `dagger-engine.collections-disk-abba-2`, ID `e7457765f81a0dde504642bdd20304d48f045d995853e3dcdd2a5c3f85ad3abc`.

Both have only `PATH`, `_EXPERIMENTAL_DAGGER_RUNNER_HOST`, and the three SDK manifest digest variables. Neither has Cloud/auth, OTEL, cache-facts, or remote-cache environment variables, and neither mounts a user credential home. Their original creator, `/tmp/collections-perf/post-rebase-io/run.py:start`, adds only the TypeScript SDK manifest environment value. No engine lifecycle operation was performed during this audit.

Engine process telemetry initialization uses no automatic exporter detection (`cmd/engine/telemetry.go:121`). The separate cache-facts exporter requires an engine token as well as explicit enablement; these engines have no token. The session's Cloud publisher remains scoped to its client metadata, including after another authenticated session has used the same engine.

## Diagnostic boundary

This is a source/configuration audit, not a packet-capture proof of arbitrary application behavior. The reviewed synthetic fixture reads and writes local workspace files; its `up` flow requests `alpine:3.22`, so image resolution or a missing cached image can still contact the image registry. That is separate from uploading session telemetry or source metadata to Cloud. Keep these samples clearly labelled as local-only lower-bound diagnostics, and retain normal Cloud-enabled comparisons as a separate series once authorized.

No Dagger commands, builds, live Cloud requests, or credential reads were performed for this audit.
