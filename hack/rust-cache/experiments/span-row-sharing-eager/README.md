# Prepare shared telemetry rows before routing writes

This refinement removes the lazy version's per-span synchronization. It is disabled after its complete-command comparison: **37.38 → 43.35 seconds median**, faster in one of four pairs. Cache pruning overlaps the two slowest candidate runs, while the remaining pairs disagree. The bulk component improves, but a reliable listing speedup is unproven. See [the assessment](../../NATIVE_TELEMETRY_SPAN_ROWS.md).

`evidence.tar.gz` retains the exact source and overlays, expected control complexity failure, race checks, malformed-route isolation check, four component pairs, all ten complete commands, diagnostic profiles, native-cache checks and final selected state. All measured commands return the same ordered 4,398 rows and exit successfully through cleanup. The excluded initialization adds a test and returns 4,399 rows.

`MANIFEST.json` records sizes and SHA-256 hashes for all **358 verified archive members**. Compressed wcprof chunks and their reconstruction driver replace the redundant expanded event file. Source-context profiles copied from `collection-query-work-budget` describe the earlier investigation; this refinement's own profiles are under `testdata/preflight/` with derived reports beside them.

The comparison preserves normal telemetry, ordinary GC, native result keys and the owned engine's volume. Diagnostic counters and profiling are off during timing. All six Rust histories reuse every compilation action before replacement, on their first candidate-enabled calls afterward and after the cohort. Cold startup is unmeasured. This is not a standalone upstream patch; no new PR or proposal is created.
