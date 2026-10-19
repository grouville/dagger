An unselected SDK decoder experiment. [Report and tradeoffs](../../NATIVE_DANG_JSON_BUFFER_DECODING.md).

Complete warm test-edited Go listing moves 6.017 → 5.896 seconds, faster in three of four pairs, with lower CPU and about 206 MB less allocation per pair in all four. Small object inputs allocate more, so this unconditional variant is retained for tracking rather than proposed upstream. No PR is open.

Both SDK race suites, 27 Go checks, 28 Rust/native-cache cases and 24 timing commands pass with their expected outcomes. Differential fuzzing covers 266,289 generated cases; the 268 interesting inputs and two failing negative controls are retained. Four lossless captures preserve 800 getter executions, 804 evaluations, 799 discovery hits and 1,415 SDK requests.

The archive excludes binaries and duplicate uncompressed streams. Every member is hashed, and all four complete wcprof streams are reconstructed byte-for-byte from their compressed chunks. Six engine source deltas extend the parent field-definition engine/CLI evidence. The standalone source is based directly on pinned upstream and adds no dependency version change. All nineteen engines and volumes remain intact, with modes/profilers/sources restored and no active requests or runtimes. Current cold/restart and Rust latency are unmeasured.

Archive: 28,208,283 bytes, 665 verified members, SHA-256 0827a141a6c0ac087db0ae747b84eee9fcd4e55b44e5dea0a0edfaa0e730f7fb.
