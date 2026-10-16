# Visit each snapshot root once during collection

The [follow-up](NATIVE_GC_ROOTS_FOLLOWUP.md) separates preparation effects from the diagnostic flag and tests a loop with one root lookup. Its natural edited-command control shows no systematic penalty, while its concurrent-collection command improves in six of eight pairs. The original loop and measurements below remain distinct; both variants are still experimental.

Deduplicating containerd's initial GC roots reduces the real cache's mark phase from **878 to 528 ms** in six fresh-process comparisons. It avoids about **169 MB and 4.76 million allocations per pass**, while retaining exactly the same objects. Complete edited 1,026-crate Rust checks during concurrent collection improve in **16/16 pairs** across two cohorts. Without concurrent collection, the second cohort is slower in **8/8 pairs**, by about 62 ms per pair. That cost remains unexplained, so this candidate is not yet ready for submission.

This targets the active containerd path used by the engine. Both CPU profiles and foreground stacks reach `core/metadata.DB.GarbageCollect` and `pkg/gc.Tricolor`. During collection, two host imports wait in `metadata.DB.Update`, trying to create their operation leases. Their call chains reach `engine/filesync.localFS.Sync` and `Host.directory`. The metadata collector holds the corresponding write lock throughout marking and sweeping. Reducing that work shortens an observed foreground wait; the change leaves the lock in place.

## The repeated work

A snapshot can belong to many leases. Containerd emits it as a root for each lease. `Tricolor` records these roots in its `seen` map, but puts every copy on its initial work stack. It then reloads references for every duplicate. References reached through child edges already use the seen map correctly.

The retained cache supplies **399,795 roots for 77,784 distinct raw nodes**; one node appears **18,418 times**. There are 77,772 canonical live nodes because some raw nodes differ only in traversal flags. The proposed loop queues each exact root once. It preserves the resource type flags and namespace during traversal, and keeps the existing canonicalization of the final live set. Independent leases remain intact.

The same loop remains in [containerd main at `c787e39387ec`](https://github.com/containerd/containerd/blob/c787e39387ec2de521a14985f6785c53dfefaad7/pkg/gc/gc.go). A standalone patch against that revision changes only the initial-root loop and adds one regression and one control benchmark to the existing GC test file. The engine experiment uses Dagger's containerd v2.2.5 dependency; its live comparison adds a separate diagnostic switch.

## Component measurement and correctness

The database was copied while the idle owned engine was frozen for 0.837 seconds, then immediately resumed. The copy passes bbolt's consistency check and is opened read-only. No snapshot data is copied or removed by this analysis. Database hashes before and after the comparison match.

Containerd's existing scanner exports the root list, references and live set. A separate breadth-first traversal checks that exported set. Both implementations then mark the copied database and must match the independent oracle exactly. Each retains all **77,772** expected nodes.

| Mark phase on the real database copy | Before median | Candidate median |
| --- | ---: | ---: |
| Elapsed time | 877.98 ms | 527.79 ms |
| Allocated bytes | 442.65 MB | 274.01 MB |
| Allocations | 7,682,884 | 2,918,367 |

Six alternating before/after pairs use a fresh process per observation, Go 1.26.6, linux/amd64 and `GOMAXPROCS=8`. Opening the copy, loading the graph, checking the oracle and an initial Go GC happen outside the timer. The mark itself runs once per process. All six pairs improve; the median paired saving is 363 ms. These are mark timings, excluding sweep and physical cleanup.

The unique-root control discloses a cost: 1,000 unique roots with no outgoing references take **262.65 → 286.79 µs**, roughly 9% or 24 µs more, with unchanged allocations. Only one of six pairs improves. One root takes 244.95 → 239.20 ns with unchanged allocations, establishing no material regression there. The extra membership lookup trades a small amount of work on distinct roots for avoiding repeated database lookups in shared graphs.

The focused regression combines duplicate roots, a cycle, different namespaces and distinct traversal flags. It checks the complete live set, one reference lookup per raw node and unchanged input roots. It fails on the original loop and passes after the change. Both containerd v2.2.5 GC and metadata suites pass with the race detector. On main `c787e39387ec`, the standalone regression also fails before the fix; the full GC package race suite and `go vet` pass afterward with Go 1.27.0. No tests are skipped. Repository-wide `make check` is not run: `golangci-lint` is unavailable and this checkout contains only the GC package and root files.

Through the actual Rust module, a new 130-action history has 0 hits, an unchanged input has 130, a used-source edit has 128, invalid Rust fails, and repair and reversion each recover 130. A real collection runs after every phase, including the failed compilation.

## Complete edited commands

Both GC implementations run in one diagnostic engine binary, selected by one atomic read per collection. Module, worker, result keys and compiler inputs stay the same. The engine restarts cleanly with its existing volume before the comparisons. The selected Rust module remains `f73c561`.

Every observation edits a used leaf and runs `check rust:packages/check`. Processes are fresh; engine and compiler state are warm. Telemetry remains enabled against the local receiver, and profiling is disabled in timed cohorts. Cases rotate between the old and new marker, with and without an added concurrent collection. Ordinary containerd collection is deferred in all arms and drained after every command; dagql pruning remains enabled.

| First cohort, 10,000-file scratch snapshot | Before command | Candidate command | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| No added concurrent collection | 1.684 s | 1.620 s | 74 ms | 5/8 |
| Concurrent required collection | 2.438 s | 2.170 s | 327 ms | 8/8 |

The concurrent collector takes 1.094 → 0.773 s. All scratch snapshots survive until collection and disappear afterward. The case timer includes command, teardown and final cleanup. Its medians are 5.192 → 3.146 s in the concurrent arm, but large I/O stalls affect that measure: one case lasts 12.329 s and host I/O pressure reaches 42.1% during an admitted command. All observations remain included.

The confirmation reverses the case order and uses a scratch snapshot containing only one file, reducing physical deletion work:

| Confirmation, one-file scratch snapshot | Before command | Candidate command | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| No added concurrent collection | 1.482 s | 1.535 s | **−62 ms** | **0/8** |
| Concurrent required collection | 2.381 s | 2.042 s | 324 ms | 8/8 |

The concurrent collector takes 0.972 → 0.626 s. All sixteen concurrent pairs improve, with a pooled median paired saving of 327 ms. The confirmation retains an 11.267-second case outlier. Maximum host I/O pressure during commands is about 2.2%; host memory pressure reaches 9.2% in one candidate concurrent observation. No admitted observations are discarded.

The idle result needs further investigation: the first cohort has five faster pairs, while the confirmation has none. No containerd collection runs inside those idle command timers, but the selected implementation also runs during preparation and post-command cleanup, which can affect subsequent process state. We have not established why the confirmation slows down. The candidate remains disabled by default, and this is recorded as a possible regression rather than dismissed as noise.

The concurrent arm performs an earlier collection in addition to final cleanup, so it is not a benchmark of a production scheduling policy or GC frequency. It establishes a complete-command effect when collection overlaps work. It does not establish an ordinary edited-command median or the Cargo +0.5-second target.

[Evidence, exact sources and experimental drivers](experiments/containerd-root-dedup/) include the exported graph, component observations, command cohorts, wait stacks, CPU profile, standalone patch and native correctness checks. The large raw database and executable binaries are excluded; repeating the database benchmark requires another consistent retained-cache copy. The [draft containerd description](upstream-prs/containerd-root-dedup.md) discloses both regressions. The [six existing Dagger proposals](upstream-prs/README.md) remain separate and await individual approval; this additional candidate belongs in containerd. No PR is opened.
