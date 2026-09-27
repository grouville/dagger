# Proposed change: skip a redundant Docker start for a running engine

A normal managed-engine command inspects the selected existing container and then invokes `docker start` even when it is running. Request the state in that existing inspect and omit start only for the exact `running` status. Keep the optional capability internal to the Docker backend; all other backends and all unknown/non-running statuses use their previous start behavior.

Use `.State.Status`, not `.State.Running`. A paused or restarting container can retain the running boolean, while start may return an error the old path exposed. This conservative interpretation preserves those errors. Missing and canceled lookups, creation races, start failures and cleanup remain covered by the focused regression tests.

This is a point-in-time observation. It does not establish atomic liveness against concurrent external stop/restart operations, add a connection retry, or replace the backend's exec authorization. There is no Dagger cache or engine behavior change.

The original branch fails the meaningful running-engine witness; candidate normal/race suites pass44 test/subtest outcomes each. The matched 32 local-command trial shows lower paired CLI/process-tree CPU, a 13.2 ms native-generation median reduction, and flat core independent wall medians. Do not claim a universal command latency improvement. See the separate runtime report and paired values.

Apply only the four exact source files in exact-source-hashes.json. The three implementation files match the frozen built overlay; the test file matches the validated test overlay. Runtime sources have not changed since validation/build. Integration and commit remain the parent task's decision.
