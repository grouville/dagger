# Current-main full Go collection diagnostic

The candidate sorting change alone did not make the complete real-repository listing finish. `dagger check --module go --check test --list --all` reached the 600-second limit without a row. This is an interrupted correctness smoke, not a latency comparison or successful output/cleanup validation. No main-versus-patch full-listing speedup can be calculated.

The fixed source is Dagger `c5456d9cbf47e432b89aba43e35211425e8e1f03`, with one unique added test: expected 4,483 rows. The engine and CLI are unchanged main `23b004afe665eb4cc8a44767ba532fcb5cda2020`, with the Go sorting patch on main `8a1d6ad09c909a541e7e5fa319bddb5dba83d20b`. Source and configuration are restored. Existing engines and volumes remain intact.

A 45-second wcprof window and a nested 15-second CPU window observe this same active workload. They do not start another collection command. The original driver's `profiling: false` field was inaccurate after enabling that observer: the untouched original result is retained beside the corrected result, which links the observer and marks profiling true. This sample must not enter an unprofiled timing cohort.

During the wcprof window, 110 `GomodGoMod.subpath` calls execute, along with 19 `Gomod.at` and 19 `GomodGoMod.selected` calls. There are nine executions each of owned-file discovery, workspace globbing, root discovery and workspace search. No `GoPackage.tests` call appears in the window; package discovery is still active. The capture has zero dropped events and no unfinished operations among those begun in the capture.

The CPU window contains 17.73 sampled CPU-seconds. Dang parsing accounts for 53.47% and background garbage collection 28.31%. These are shares of sampled CPU, not wall-time shares; cumulative parser rows must not be added. The profile is a concrete lead for module-loading reuse and repeated helper work, not an attribution of the full gap.

The older ~45-second successful listing used a different, combined experimental engine, CLI and Go module and an older source inventory. It is not a controlled comparison with this diagnostic. The independent sorting PR claims only its separately validated complete owned-file command, 19.76 to 3.15 seconds.

`root-path-candidate.patch` is a separate, unverified experiment on Go main. It uses the documented identity that a path relative to the root module is already a workspace path. It contains no sorting patch. Its performance and correctness must be checked independently before publishing.
