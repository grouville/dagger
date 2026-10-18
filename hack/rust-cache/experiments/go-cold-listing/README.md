# Cold Go collection listing evidence

[Results and conditions](../../NATIVE_GO_COLD_LISTING.md): three new engines and independent empty cache volumes; 12 complete listing commands; all expected rows and exits correct.

`evidence.tar.gz` contains the driver, plan and exact selected flags, source/config restoration, per-command stdout/stderr, CLI resources, engine CPU/memory/pressure counters, initial engine creation records and clean stop records. Engine logs and the final identities of the untouched original engines are included. The engine image is already local, the host page cache remains warm, and no image download or source checkout is timed.

`summary.json` distinguishes readiness, first-command time and total engine-start-to-first-result time. `archive.json` records the archive SHA-256 and size; every member is verified against `manifest.json`.

The source stack is preserved in the preceding [discovery-screen archive](../go-discovery-screens/). Its shared-function-metadata experiment is disabled throughout this study. No new production patch or PR is introduced.
