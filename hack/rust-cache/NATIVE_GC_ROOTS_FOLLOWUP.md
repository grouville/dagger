# Separate collector work from its effect on the next command

The ordinary edited 1,026-crate check takes **1.552 s with the original collector and 1.548 s with a refined deduplication loop**, versus **0.766 s for Cargo**. No collection overlaps those commands. Four of eight pairs improve, so this establishes no ordinary-command speedup. The Cargo +0.5-second target remains about 0.28 seconds away on this workload.

When collection is deliberately overlapped with compilation, the refined collector takes **1.009 → 0.667 s**, improving in all eight pairs. The complete command improves from **2.445 → 2.255 s**, with six of eight pairs faster. This is a conditional benefit. The original candidate's earlier 16/16 wins belong to its earlier loop and cohorts; they are not results for this refinement.

The [original containerd draft](upstream-prs/containerd-root-dedup.md) remains under validation. Both loop variants are available for review; neither is enabled by default. The six prepared Dagger proposals are unchanged, and no PR is opened.

## The idle penalty follows preparation

The original confirmation had an approximately 62 ms paired penalty without concurrent collection. Its recorded events show no real containerd collection overlapping those command timers. During normal engine work the diagnostic flag is read only inside the marker, so it cannot directly slow the command when the marker never runs.

A separate 32-command experiment crosses two factors: the original or first candidate algorithm used to prepare and clean up the snapshot store, and the flag selected only during the command. All commands edit a used leaf in the same workspace and retain telemetry. Eight rounds balance all four combinations and their immediate predecessors. Actual collection overlaps are asserted absent.

| Comparison | Median paired saving | Faster pairs |
| --- | ---: | ---: |
| Change command flag after original preparation | −10 ms | 3/8 |
| Change command flag after candidate preparation | 14 ms | 5/8 |
| Change preparation, command flag off | −95 ms | 2/8 |
| Change preparation, command flag on | −61 ms | 3/8 |

Changing the flag alone has no consistent effect. Changing preparation reproduces a penalty. Candidate preparation precedes four commands containing a Go GC cycle, versus one with original preparation; their median initial heaps are 5.77 and 4.67 GB respectively. Each command allocates about **460 MB** in the engine. These observations identify preparation and memory pacing as relevant, without proving that Go GC explains every millisecond. This accumulated benchmark engine is not a measurement of a new project's heap or evidence of a leak.

Four diagnostic commands force Go collection outside their timers and capture wcprof and allocation profiles. None contains a Go GC cycle. One allocation difference profile reports about 473 MiB, including profiling overhead; it is not another measurement of the unprofiled 460 MB. Telemetry encoding/forwarding, query evaluation and filesystem operations contribute. These are investigation targets, not savings already achieved. A CPU check of the span-child index accounts for only 0.03 sampled seconds out of a separate 21.69-second capture, so that suspected quadratic path is not selected for optimization.

## Avoid a second root lookup

The first candidate tests membership and then inserts a new root. The alternative inserts once and queues the root only if the map grows. It preserves the exact node identity, input slice and reference traversal. It introduces no lock, retained state or dependency. A second alternative builds the initial stack from the map's keys.

Eight rotating fresh-process rounds compare all four loops against the same read-only retained database, validating the identical 77,772-node retained set against the independent oracle:

| Initial-root loop | Real mark median | Allocated bytes | 1,000 unique roots, no references |
| --- | ---: | ---: | ---: |
| Original | 949 ms | 442.7 MB | 302 µs |
| Membership then insertion | 560 ms | 274.0 MB | 338 µs |
| Insert, check map size | 541 ms | 274.0 MB | 298 µs |
| Build stack from map keys | 592 ms | 261.1 MB | 307 µs |

All deduplicating loops improve the real mark in all eight rounds. The size-check loop beats the first candidate in five of eight pairs, saving 11 ms in the median pair. It improves the unique-root control in only four of eight pairs against the original loop; that is not proof of a general unique-root speedup. These observations are noisy: maximum host CPU and I/O pressure over whole benchmark processes, including fixture loading, are 43.9% and 6.5%. All observations remain included. The map-key variant changes traversal order and has no established overall advantage; it remains unselected.

The size-check loop is tested in a diagnostic engine with the original loop behind the same existing switch. All 44 Dagger overlays remain identical; one local containerd source overlay changes. The owned engine stops cleanly in 128.088 seconds before installation and preserves its volume. The shutdown still uses the preceding binary, so its duration cannot be attributed to the new loop.

## Complete commands

Both series use Rust module `f73c561`, Rust 1.77.2, eight workers, fresh CLI/helper processes, warm engine/compiler state and telemetry enabled against the local receiver. Every observation edits a used Rust value. Profiling is off. Results from different scopes are not added together.

| Natural collection, eight rotating pairs | Command median | Commands overlapping collection |
| --- | ---: | ---: |
| Original | 1.552 s | 0/8 |
| Size-check loop | 1.548 s | 0/8 |
| Native Cargo | 0.766 s | 0/8 |

There is no scratch snapshot, forced collection between cases or forced Go collection in this series. Native Cargo runs `cargo check --workspace --locked --offline`, with incremental compilation and a target directory outside the imported source. Maximum admitted-command host I/O pressure reaches 6.7%; all samples remain included.

The forced-collection series uses the earlier reversed order and one-file scratch fixture. Ordinary containerd collection is deferred in both arms and drained after each case; dagql pruning remains enabled:

| Controlled series | Original | Size-check loop | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Concurrent collector itself | 1.009 s | 0.667 s | 345 ms | 8/8 |
| Complete command during collection | 2.445 s | 2.255 s | 193 ms | 6/8 |
| Command without concurrent collection | 1.522 s | 1.648 s | −81 ms | 3/8 |
| Command, teardown and final cleanup, concurrent arm | 3.678 s | 3.050 s | 660 ms | 7/8 |

The preparation-related idle penalty remains visible here, despite its absence as a systematic effect in the natural series. Two concurrent command pairs are slower even though their collector jobs improve. One has substantially greater engine CPU use; another has less engine CPU but more elapsed time. Maximum host I/O pressure is 28.2%. These observations do not establish the cause of either loss. There are no discarded observations; the longest whole case is 3.803 seconds.

## Correctness and next work

GC and metadata race suites pass for both alternatives on containerd v2.2.5. The size-check patch also passes containerd main's complete GC race suite and `go vet` with Go 1.27.0, without skipped tests. Its regression is unchanged from the archived test that fails against the original loop. Repository-wide lint remains unrun because `golangci-lint` is unavailable.

On the installed engine, native Rust compilation checks cold results, reuse, a used-source edit, invalid Rust, repair and reversion, with actual collection after every phase. All six retained histories then recover every action: 130/130, 1,026/1,026 and 6/6 in each of two histories. Compiler result keys, worker code and incremental-state policy are unchanged.

The normal edited-command gap remains the next target: source import and helper work dominate the observed critical path, while the allocation captures expose substantial repeated encoding and decoding. Reducing those costs needs a separate experiment. Neither the collector optimization nor the allocation profile establishes the full performance target.

[Raw samples, exact sources, standalone patch, test logs and profiles](experiments/containerd-root-dedup-followup/) preserve both successful and slower observations. The large raw database and executable binaries remain excluded. The final state restores ordinary collection and disables both profiling and the experimental root switch.
