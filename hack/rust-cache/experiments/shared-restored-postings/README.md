Standalone patch base: ff0b029a4d270a651b9a8c7286babc79089066e4. Review branch: perf/shared-restored-digest-postings.

`evidence/standalone.patch` applies at that revision. Source snapshots and all resolved diagnostic-engine overlays are under testdata, with hashes in engine-sources.json. The engine also retains previous experiments; its identity and complete overlay are recorded.

The import benchmark uses three alternating pairs with warm filesystem cache and fresh Cache objects. Close is outside its timer. Every iteration asserts a non-reset import and expected result count. An invalid earlier discard-close benchmark is preserved under an explicitly invalid directory and excluded from all claims.

The two complete listing measurements use the final Go module, fresh source comments, telemetry and normal GC. No compiler/test workload starts. These are repeated observations after a cache reopen, not an alternating engine-binary A/B. The later wcprof/CPU capture is diagnostic, not a timing arm. Raw NDJSON is gzip-compressed without changing its bytes.

A read-only Docker log client stalled after the graceful replacement; that client alone was terminated. Initial and resumed activation evidence are preserved. The engine and its cache were not forcibly stopped or reset.

The previous interface candidate remains disabled: both full-command candidate attempts failed session cleanup. Its failed cohort is retained separately.
