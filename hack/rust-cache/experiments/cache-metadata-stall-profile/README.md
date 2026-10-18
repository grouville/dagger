# Cache-maintenance diagnostic

See [the analysis](../../NATIVE_CACHE_COMPACTION_INDEXES.md). This is a diagnostic workload, not a before/after optimization comparison. It retains all fourteen preparation listings, all six captures, numbered raw wcprof chunks, CPU and lock profiles, source provenance, the corrected CPU analysis and its earlier derivation error, and the retained Rust cache checks. All twenty complete listings return the same 4,398 rows. Compaction is captured once; no net result eviction is observed.

Concatenate the evidence.tar.gz.part-* files in numeric order, then extract the resulting gzip tar archive. MANIFEST.json gives every member and part hash. The redundant complete wcprof files are reconstructed from their archived chunks; reconstruction was checked byte for byte. Original absolute paths describe the measurement host and need adapting for replay. No engine binary or cache volume is included.
