# Workspace-search CI fixture correction

PR: https://github.com/dagger/dagger/pull/14740

The supplied CI trace, `67b7a56db045dbc65df8ad24582b6701`, has 980 passing tests and two failing cases in the newly added scoped-search integration test. The test relied on ripgrep being installed on the test host. CI's BusyBox grep cannot handle the `-b` argument used by the fallback. The mixed-source case fails before returning results; the missing-file case gets a generic grep failure instead of its expected diagnostic.

Commit `fecceeb7b554b50c525d448c967113caabd4c71a` changes only the test fixture. It uses `nativeWorkspaceBase` and installs ripgrep, matching the existing host-overlay search test. All four cases remain. The missing-file assertion uses the existing `requireErrOut` helper to inspect nested CLI stderr and also checks the missing filename. No production code changes.

The same test binary is run against the retained stock and patched engines. On stock, exactly the three intended regressions fail; the missing-path control and three existing search/glob cases pass. On the patched engine, all seven cases pass. These are correctness checks, not performance measurements. The patched engine's production workspace.go blob is `ed6365c22d98fb6bae5339b3bdcf5af92a54525a`, identical to the published PR. Its source base is c5456d9cbf; the published PR is based on ce6dc9f940.

Attempt 01 exposed that a nested CLI's stderr must be read with `requireErrOut`, rather than from the SDK error message. Attempt 02 caught a local beta.19 CLI / beta.20 engine mismatch. Attempt 03 caught a dynamically linked local CLI that could not run in Alpine. Final verification uses the matching static beta.20 CLI on the patched engine and the original beta.19 CLI on stock. These harness failures remain recorded; none is reported as a passing check.

The full CI suite has not been rerun locally. The branch push requests normal upstream CI. Existing engines, volumes, telemetry and cache policies are preserved.
