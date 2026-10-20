# Combined Go discovery: real-repository attempt

The complete `dagger check --module go --check test --list --all` command on `dagger/dagger` still reaches the 240-second timeout with zero rows. It uses Go package-scoped search plus the root-module path identity case and batched main-package selection. Expected inventory is 4,483 rows, including a newly added test. No timing gain or correctness success is claimed. Source and installed-module configuration are restored afterward.

Fresh CLI on the retained stock engine, telemetry enabled, no profiling, ordinary cache policy. A short git commit amendment/push to repair the user-requested DCO trailer happened during the attempt; this failed diagnostic is not an independent latency benchmark. The result records timeout and interrupted cleanup explicitly.
