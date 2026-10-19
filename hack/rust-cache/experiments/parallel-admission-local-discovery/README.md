# Parallel admission on the selected Go module

**Unselected:** complete listing regresses after both edit types. See the [report](../../NATIVE_PARALLEL_ADMISSION_CURRENT.md). No production code or benchmark-engine binary changes in this study.

`assessment.json` records four balanced pairs per workload, 27 Go check invocations, 28 Rust/native-cache cases and the corrected profile counts. Both modes use Go module `511d381`. `final-state.json` verifies all nine retained binaries and cache volumes, restored workspaces and disabled capture settings.

`evidence.tar.gz` contains:

- `admission/`: scripts, identities, all command samples and output, behavior checks, four successful lossless captures, CPU profiles and critical-path analyses. `initial-profile-cleanup-error/` retains the failed script attempt and recovered raw buffer; it is not counted as a successful capture.
- `allocations/`: a separate command in the selected mode with before/after allocation profiles and exact runtime counters. `assessment.json` explains sample lag and the corrected denominator. The initial `-diff_base` output remains beside the corrected `-base` analysis.
- `source-parent.json`: the unchanged source and binary evidence parent, identified by hash. Its own source-parent references remain necessary.
- `wcprof-reconstruction.json`: exact hashes and event counts for the five successful reconstructed streams. Raw gzip chunks are retained; duplicate uncompressed streams and executable binaries are excluded.

`manifest.json` records every archive member's size and SHA-256. Every member was verified after compression; `archive.json` identifies the archive. `admission/archive.py` contains the packaging and stream-verification procedure.

The separate SDK element-type correction is [recorded independently](../dang-list-element-types/). It is not installed in these engines and is not counted as a speedup. Current cold and Rust latency remain unmeasured.
