# Avoid quadratic child-span indexing

The later [full Go listing comparison](NATIVE_GO_WIDE_TRACE_INDEX.md) shows a larger-workload benefit: **53.58 → 46.72 seconds** in three successful paired comparisons, with 7.05 seconds median paired saving. All four optimized attempts succeed; one control times out during shutdown. A new session's index otherwise performs over two billion ordinary-child comparisons. Earlier Rust results below remain unchanged.

The telemetry store scans an existing child list whenever it indexes a new span. A wide trace therefore performs quadratic work. Reusing information already in the parent map removes that scan for new span IDs. Cause links can similarly use their existing reverse index to avoid scanning every span linked to a shared target.

The standalone patch is pushed as the tenth upstream proposal. It adds no map, lock or retained state. The original small-workload results below did not establish a firm command-latency gain and initially left the optimization disabled. The larger Go follow-up is recorded separately above.

## Verify the active path

The selected listing profile attributes about **460 ms of CPU** to the ordinary child-list loop. This is `engine/clientdb`, reached through the running engine's span exporter and telemetry store. Its production file is byte-for-byte identical on upstream main `717589c9cc`, verified against the live main ref before extraction.

The parent map already records whether a span ID has had a parent. A new ID cannot already occur in a child list. Existing same-trace duplicate suppression remains in place; IDs repeated across traces retain the old span-ID-only uniqueness scan. The new test also covers a parent first appearing after the initial snapshot.

Cause-parent and cause-child lists are populated together by the same function under the existing mutex. Checking the linking span's targets is sufficient to preserve both directions and their order. Later snapshots still add new links. No other production code writes these maps. The full `clientdb` race suite and the new compatibility test pass on the standalone patch; the compatibility test also passes on main.

## Fresh-index components

Each iteration constructs a new index and inserts all rows. Span fixtures and mixed 16-character IDs are prepared outside the timer; there is no persistent warm index. The benchmark targets `spanLookup.addLocked`, with cause links already decoded; stream I/O and link decoding are outside this component. Six fresh-process A/B and B/A pairs run directly on main with the patch, Go 1.26.6, linux/amd64, Intel Core i5-9300H, `GOMAXPROCS=8`, 150 ms per case.

| Children sharing a parent or cause | Parent index, main → patch | Cause index, main → patch |
| --- | ---: | ---: |
| 1 | 0.890 → 0.822 µs | 0.891 → 0.879 µs |
| 1,026 | 1.878 → 0.462 ms | 1.978 → 0.484 ms |
| 4,096 | 24.742 → 1.942 ms | 25.511 → 2.099 ms |

Allocation counts are unchanged: 166 for the 4,096-parent case and 4,262 for its cause-link counterpart. Byte counts differ only by a few bytes of measurement variation. The ordinary parent case becomes linear in the number of new children. Cause-link insertion no longer depends on the number of other spans pointing to the same target; it still checks the linking span's own targets.

An earlier component fixture used sequential IDs. Its 4,096-parent result was **29.44 → 1.96 ms**. The separate mixed-ID screen repeats **24.57 → 1.94 ms**, before the standalone-main comparison above. All observations are retained. Main component pressure peaks at 0.6% CPU, 2.1% I/O and 0.1% memory.

## Complete commands and profiles

Two eight-pair cohorts cover edited checks, tests and listings. A final 16-pair cohort targets the remaining listing uncertainty. All use the same physical sources, module `da1ae47`, native histories and reversible engine `3254774b…`. Both direct artifact-string policies remain selected in both arms. Every command has a fresh used Rust edit and CLI process; compiler/engine caches are warm. Telemetry through the local receiver and ordinary collection stay enabled. No GC is forced. Timed runs disable wcprof and the comparison counter.

| Complete edited 1,026-package listing | Original | Patch | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Initial eight pairs | 2.498 s | 2.394 s | 170 ms | 5/8 |
| Confirmation eight pairs | 2.573 s | 2.445 s | 135 ms | 5/8 |
| Final sixteen pairs | 2.400 s | 2.335 s | 71 ms | 10/16 |

Across all **32** listing pairs, median paired saving is **119 ms**, with **20/32** faster pairs and **0.351 CPU-second** less engine CPU per pair. CPU is lower in 19/32 pairs; allocations show no established reduction. A descriptive paired bootstrap interval for median latency saving spans **−16 to +200 ms**. It includes zero, and these cohorts do not establish a general full-command improvement.

Across the two full cohorts, large checks save **−9 ms** per pair, direct checks **+10 ms**, and small tests **−9 ms**, each faster in **8/16** pairs. Initial direct-check slowdown reverses in confirmation. No compilation gain or regression is established.

All admitted observations are retained. Host CPU pressure reaches 31.1%, 29.8% and 32.4% across the three cohorts; confirmation I/O reaches 32.6% in a direct-check control. No timed command overlaps a recorded snapshot collection. All listings contain the expected 1,026 packages. These generated path-dependency workspaces do not establish registry, build-script or procedural-macro support or production Cloud latency.

Separate completed captures have zero dropped events and open operations. The listing's ordinary new-parent path would scan **88,993,812 existing children**, identically in both captures; the patch skips those comparisons. The large check has **1,604,697**. Both listing captures retain 5,466 result publications. Sampled indexing CPU falls **0.58 → 0.11 CPU-second** in the five-second diagnostic windows. These profiles demonstrate the local mechanism, not a repeatable command-latency saving.

## Selection and upstream review

The [standalone branch](https://github.com/grouville/dagger/tree/perf/upstream-span-lookup-fanout), `330c7d635c97e53a089de033137106fd10d3277e`, changes one production file and adds the compatibility test and benchmark. It is based directly on main `717589c9ccacbba7d3cf902647aa5c9ca68085e8`, independent of the other nine proposals. Its [description](upstream-prs/span-lookup-fanout.md) leads with the component scaling and discloses mixed full-command results. No PR is open.

Adversarial review focused on map invariants, IDs repeated across traces, parent changes, late cause links, ordering and lock scope. Existing first/latest-row selection and marker handling are untouched. The change removes work inside the current critical section and adds no synchronization or memory ownership mechanism. The rare cross-trace collision case retains its linear scan.

All six retained native histories pass with the optimization enabled: **130/130**, **1,026/1,026** and **6/6** cached compiler actions, twice each. Preparation first compiles the last edits left by Cargo or listing controls. These unchanged inspections verify cache preservation only.

Those Rust cohorts use diagnostic binary `3254774b3a3e53f98adb383c4eafd9cf2613d3612c6bcec2aab8fa12eeabed7b`, with this optimization disabled outside comparisons and the selected artifact getters enabled. Temporary counters/profiling are off after the cohort; ordinary snapshot collection is enabled. [SELECTED_BASELINE.json](SELECTED_BASELINE.json) records that Rust baseline's source manifest. The Rust module stays `da1ae47`. The newer Go follow-up records its own binary and source identities.

The [shared digest-mount experiment](NATIVE_DIGEST_PATHS_MOUNT.md) also stays unselected: its small component gain does not justify duplicated path validation. The next broad workload comparison should revisit shared-library and deep-chain edits with the latest selected stack; this turn's timed checks edit a leaf. The broader native Rust-cache performance goal remains incomplete.

[Raw evidence](experiments/span-lookup-fanout/) retains all three command cohorts, both ID distributions, standalone-main tests and components, counters, profiles, pressure, source manifests, retained-cache verification and final runtime settings.
