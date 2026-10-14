# Reuse resolved parents while copying directories

The 102-action workspace spends measurable time resolving destination directories while copying retained Rust incremental state. In two instrumented shared-edit captures, that copy took 108.5 and 93.1 ms; directory preparation accounted for 43.4 and 39.3 ms. The traversal already knows each parent's resolved destination, but child directory creation resolves the ancestors again.

[The isolated engine change](https://github.com/grouville/dagger/commit/629b12a18) carries that parent through both included directories and the pending directories created by include filters. Existing symlinks and replacement cases fall back to the original resolver. Metadata application is preserved. The change adds no locks or persistent cache.

Six sequential, alternating pairs of a focused 102-directory copy benchmark reduced the median from **20.56 to 16.77 ms** (18%). Every candidate sample was faster; median paired saving was 4.79 ms. This measures copying selected state directories, not a complete Dagger command.

Complete commands use the real Rust module, fresh edits, telemetry enabled, and Cargo controls. Both engines include the same bounded parser experiment. The first series has eight pairs per scenario; the second swaps engine binaries while preserving the engines' cache volumes and has ten pairs per scenario.

| Edited command | First series: original → candidate | Crossover: original → candidate | Candidate faster, first / crossover |
| --- | --- | --- | --- |
| Test, small workspace | 1.045 → 1.006 s | 1.106 → 1.011 s | 6/8 / 6/10 |
| Check, leaf in 102-action workspace | 0.840 → 0.761 s | 0.819 → 0.760 s | 6/8 / 9/10 |
| Check, shared dependency | 1.403 → 1.357 s | 1.574 → 1.479 s | 5/8 / 5/10 |

The isolated copy improvement is repeatable. Leaf edits also favor the candidate in both series. A general complete-command gain remains unproven: shared edits are inconsistent, and host I/O pressure reached 77% in the first series and 76% in the crossover. CPU pressure reached 73% in the crossover. Small-workspace copies are too short to explain all of their apparent command savings. Keep this as an isolated candidate rather than attributing every timing difference to it.

Validation includes the focused layercopy suite with the race detector, a nested destination-symlink case with and without an include filter, 108 native compiler cache-hit probes, and twelve wcprof captures with no dropped events or open operations. Actual module checks fail on invalid Rust and changed runtime data, pass after restoration, preserve 5/5 compiler hits after a clean engine restart, and reuse 2/5 actions on the next application edit. The destination implementation was checked against upstream main on October 14; it still repeats these ancestor lookups.

The branch is pushed to the fork for review. No upstream PR has been opened for this experiment.
