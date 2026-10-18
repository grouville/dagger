# Collection work amplification

See [the assessment](../../NATIVE_COLLECTION_WORK_AMPLIFICATION.md). The normal command remains 35.12 seconds median. Real discovery without artifact rows takes 25.02 seconds; frozen names in normal nested collections take 9.40 seconds. These are diagnostic controls, not additive phases or an optimization result.

The archive preserves all fifteen final commands, the failed initial block, API/schema/harness corrections, source and frozen fixtures, four lossless wcprof captures, source-aligned CPU reports, exact identities, added/removed-test checks, restoration and the next experiment's acceptance criteria. No PR is opened and no engine implementation or default module changes.

MANIFEST.json verifies each archive member and the archive itself. Extract evidence.tar.xz and run evidence/rebuild-traces.py to verify the combined recorder traces. Every event is retained; per-chunk metadata preserves string prefixes, open-operation snapshots, event boundaries and original hashes without storing duplicate headers. Original absolute paths and the local telemetry receiver need adapting for replay. The exact engine source and dependency context remain in the preceding [log flush archive](../log-flush-buffer/); binaries and the engine volume are excluded.
