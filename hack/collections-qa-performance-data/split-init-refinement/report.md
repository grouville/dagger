# Shared lightweight PID1: source refinement

This refines the earlier split-init experiment; it is not applied to production source and has no new whole-command timing.

The PID1 signal/session/TTY/reaping implementation now lives once in `engine/session/initexec`. Both the original combined helper and the lightweight command call it. The heavy helper retains its legacy argv modes. A byte comparison confirms that the original `mainInit` body is identical after substituting the function signature and helper argument. Providers still run in their own process, away from PID1's global child reaper.

The refined executor mounts the second helper only for a nested client with an actual client ID or an explicitly supplied `DAGGER_SESSION_TOKEN=` environment entry, including an empty value. Ordinary execs keep their single reserved `/.init` mount, and `NoInit` keeps zero injected mounts. This is narrower than the measured earlier prototype, which mounted both binaries for every initialized exec. Therefore do not transfer its whole-command measurements to this refinement.

## Completed validation

- The first source revision passes normal/race readiness, exit/argv, signal forwarding and real controlling-terminal tests. The TTY payload verifies its foreground process group, dimensions, resize delivery and forwarded termination. Both command entrypoints compile.
- The subsequent mount refinement passes normal/race gates with nine mount scenarios plus their parent test: ordinary/nested execution, explicit/empty token, similar/bare keys and NoInit combinations. The original shared PID1 code and its tests did not change in this refinement.
- The privileged PID-namespace orphan-reaping test is explicitly skipped by ordinary host gates. A separate, isolated no-network container gate then passes real PID1 orphan reaping and TTY handling, with no skips. Its read-only rootfs has only the test binary mounted and a temporary tmpfs; the owned container was removed.

Five first-revision gates, two changed-mount gates and the separate PID1/TTY namespace gate pass. Test durations are build/test operation durations, not UX benchmarks. No engine or Cloud calls have run in this refinement. Temporary overlay package directories were removed after each test run.

The source-only review confirmed that `injectInit` precedes OCI spec construction, and that `setupNestedClient` is the only later writer of the exact session-token key. The predicate must be revisited if that setup contract changes.

## Remaining work

Before adoption, package/build both binaries on supported architectures and validate actual nested Go/TypeScript/Python calls plus normal/NoInit/service execution with the conditional mount. Then compare whole commands separately. The new reserved helper path still exists for nested/explicit-session execs; its compatibility needs explicit review. Existing readiness-pipe error-path behavior was preserved, not silently repaired in the extraction.

`manifest.json` and `prototype.patch` describe the current source; `snapshot-v1` retains the exact prior source used by `validation-v1`. `validation-v2` records only the changed mount gates. Raw test logs and binaries remain outside the repository. This does not add a workspace/result cache, alter cache policy or change Dagger's user-facing commands.
