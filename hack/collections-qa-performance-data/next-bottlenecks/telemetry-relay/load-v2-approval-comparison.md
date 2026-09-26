# Relay v2 authorization discrepancy audit

The launch was rejected before process creation. `load-v2-launch-blocked.json`
preserves the exact command, justification, and rejection text, without credentials.
No result directory or private spool was created. No retry has occurred.

The reviewer identified three missing authorizations: telemetry payload, Cloud
destination, and side effects on what it described as a shared engine. The prior
completed `ts-static-trial-2/measurements/provenance.json` identifies the same
task-owned `dagger-engine.collections-disk-abba-2`, the same greetings fixture,
the same CLI, and `check -l --all`. The new driver has no Docker engine lifecycle,
image replacement, source edit, or deletion commands. Normal listing can populate
engine caches and generates the same categories of telemetry as before.

A read-only private-config check emitted only a boolean and confirmed the target
remains exactly `https://api.dagger.cloud`. The same private endpoint/admin-file
configuration is used; neither config nor credentials were copied or logged.
The v1/v2 relay source diff adds transport and queue counters only, keeping the
original payloads, recipients, forwarding/authentication, four workers, and
128 MiB pending limit. The tested binary matches the archived v2 source hashes.

The material new workload is forty serial CLI commands: four warmups, sixteen
paired measurements, and twenty commands in two sustained blocks. In each
ten-command block there is no intentional wait for remote delivery between CLI
invocations, so multiple sessions can have exports pending concurrently. This
is the intended backlog/throughput test. A final successful drain is required;
errors fail the trial and pending accepted data keeps the daemon alive.

This comparison establishes technical continuity with the earlier trial. It
does not independently establish the exact earlier user-authorization wording;
the parent agent has the earlier approval and session context. Await that review
or explicit user approval before any live retry.
