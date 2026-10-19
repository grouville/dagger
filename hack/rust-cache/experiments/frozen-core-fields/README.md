This experiment reuses immutable core field definitions while preserving private clients and all collection getter executions. [Report](../../NATIVE_FROZEN_CORE_FIELDS.md). [Prepared description](../../PR_FROZEN_CORE_FIELDS.md). No PR is open.

The complete warm test-edited command moves 6.319 → 6.186 seconds in four alternating pairs, with roughly 524 MB less allocation per pair. Source-edit listing is effectively flat. Cold/restart and Rust latency effects are unmeasured.

The evidence archive retains all attempts, component and pipeline validation, four lossless wcprof streams, CPU/allocation profiles and source snapshots. Full streams are reconstructed byte-for-byte from their compressed chunks; binaries and duplicate uncompressed streams are excluded. Each archived member has a verified SHA-256 digest. The source-parent manifest points to the common COW engine and CLI evidence; seven source deltas reconstruct this experiment. A separate supplement retains unchanged overlay inputs omitted from the inherited manifest; the initial archive assertion and correction are preserved. The parent measured test snapshot is retained even though its later review layout changed.

The archive is 28,686,796 bytes, with 416 verified members, SHA-256 3f0a1feecd1038e29d67d9592273c1e84b727c82e21843b34953cf6c3c70356f.

All 18 engines and volumes are retained, with original binary identities verified and no active requests or runtimes. Diagnostic counters and profilers are off in the final state. Timing modes differ only in consumption of immutable field metadata; COW is enabled in both.
