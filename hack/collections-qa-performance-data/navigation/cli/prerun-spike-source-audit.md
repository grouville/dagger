# First production pre-run spike: source audit only

Observed in the first production diagnostic (`diagnostic-0-core-base`): `cli.pre_run` is 1016.791147 ms while `cli.labels` is 1.839301 ms. Subsequent diagnostics in that trial are approximately 1.996–2.320 ms for pre-run, with labels 1.797–1.998 ms. This localizes about 1015 ms outside label enrichment, before engine connection. It does not identify the responsible function.

The harness sets DO_NOT_TRACK=1 and DAGGER_NO_UPDATE_CHECK=1. Consequently analytics.New returns a no-op tracker and the update checker immediately returns. The workspace flag policy and progress-default code do no network operations. `startOAuthTokenRefresher` synchronously reads/parses the LLM configuration through `enabledOAuthProviders`, then starts an optional background refresh loop; the first inline setup contains no token refresh request. Disk/scheduling delay in those local operations is still possible and unmeasured.

The remaining explicit synchronous network-capable path in PersistentPreRunE is `checkCloudToken` (`internal/cmd/dagger/main.go:426`), which always calls `auth.Token(ctx)`. `Token` (`internal/cloud/auth/auth.go:233`) reads and decodes the stored login file; a valid token returns immediately, but an expired token invokes the OAuth token source synchronously and persists the refreshed token. Persistence takes a file lock and atomic rename. A successful refresh can therefore make later fresh CLI processes fast through the updated file. There is no general per-process auth memoization in this path, and the earlier local warmups used an empty auth configuration, so they did not validate or refresh the normal login.

**A first refresh is a plausible explanation, not a finding.** These diagnostics did not instrument auth.Token, its HTTP call, file reading or lock acquisition. No credential file was read or inspected during this audit, and no expiry/refresh state can be inferred from the existing numeric records. An OS scheduling/storage pause remains an alternative. Existing CLI HTTP diagnostics instrument only telemetry/analytics requests, so an OAuth request would not appear in those rows.

Smallest next diagnostic addition, without changing behavior:

1. Time `checkCloudToken` as `cli.cloud_token_check` and the synchronous `startOAuthTokenRefresher` call as `oauth.setup`; retain the existing finalizer timing separately.
2. If cloud_token_check carries the delay, time the existing read/decode, OAuth refresh and save calls inside auth.Token as `auth.read_decode`, `auth.refresh` and `auth.persist`. Phase presence is sufficient to count attempts. Use only static names/durations/error booleans; do not expose token fields, expiry, credentials path, URLs or OAuth responses.
3. If persist dominates, wrap the existing TryLockContext and rename/write section independently; preserve lock/context behavior exactly.

Do not force token expiry or alter credentials to reproduce this during routine perf work. Capture a naturally occurring slow command with the extra boundaries. Existing low-ms commands can validate observer overhead but cannot prove the first-run spike is fixed.

There is also a separate source-level observation: checkCloudToken consults stored login unconditionally, while GetCloudAuth later prioritizes DAGGER_CLOUD_TOKEN. Avoiding work on an unselected credential source could be considered independently, but changes to login/error UX need explicit tests and this trial does not establish a gain for that case.
