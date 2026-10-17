# Compact class mapping evidence

The compact bit index improves all twelve symbolic comparisons and all eight populated-cache comparisons. This is cache maintenance, not a complete-command speedup. The retained engine is unchanged. See [the study](../../NATIVE_CACHE_CLASS_MAPPING.md) and [review description](../../upstream-prs/cache-class-mapping.md).

Extract `evidence.tar.gz` to inspect the original files under `testdata/`, which Go package discovery ignores. The manifest records their source paths, sizes and SHA-256 hashes; every archived member was verified. Five large test binaries are omitted.

The archive retains the unchanged map control, rejected dense array and selected-for-review bit-index sources; corrected patches matching those exact sources; all 36 symbolic and 16 populated-cache processes, their balanced orders, admission and host pressure; focused and full race checks; the standalone branch's source, patch and provenance; and the unchanged selected-engine state. No full-command cohort ran with this new algorithm installed.

Both index construction and compaction are timed. Every benchmark process starts fresh, ordinary GC remains enabled and no GC is forced. Fixture construction and validation are excluded. Populated-cache runs retain live counts, validate derived indexes and require a cache hit after compaction. The sparse symbolic case allocates about 40 kB more; that tradeoff remains part of the result.

Overlay and driver paths refer to the original temporary checkouts and need adjustment for replay. The standalone patch applies directly to `ff0b029a4d270a651b9a8c7286babc79089066e4`. Its full DagQL race suite passes. No PR is opened.
