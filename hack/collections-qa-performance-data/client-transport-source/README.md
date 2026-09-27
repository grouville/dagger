This is a held, isolated shared-HTTP/2 transport prototype, not an applied production change. Normal and race tests pass, but the 90-command local matrix has mixed performance and a consistent warm-generation regression. See the separate runtime evidence allowlist under `runtime-v2/evidence-v1`.

The production patch preserves per-request authentication and cancellation while sharing only a per-Client transport. It reduces configured warm tunnels from three to two. Physical ownership explicitly joins established connections and pending dials. The earlier owner that did not fully join cleanup is retained only for its fail-first regression witness.

The unchanged-source topology witnesses and pre-correction ownership witness fail as intended. Corrected normal and race suites pass. `validation-v1--results.json` contains exact test commands, names, outcomes and source hashes; no raw test logs are published.

Both new CLI binaries were built from the same HEAD85 source, parent-metadata v2 overlay, original otel-go dependency bytes and flags. The v3 normalized Stat oracle is test-only. Build manifests record hashes; binaries and unrelated dependency source copies are not included here.

Nothing in this archive claims a cold-start win, Cloud win, universal HTTP2 one-connection limit, or 500 ms across the mixed-SDK listing. The measured candidate remains held until the generation behavior is understood.
