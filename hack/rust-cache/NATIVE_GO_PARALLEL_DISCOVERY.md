# Discover Go module packages concurrently

Two before/after orders of the full Go listing measure **85.35 → 72.37 s** and **86.27 → 70.11 s**. All four commands succeed with identical 4,398 rows. The median is 85.81 → 71.24 seconds. This is a Go-module change using an existing Dang feature; the listing is still slow.

`Go.packages` reduced the list of modules while reading each one's package paths. That serialized independent discovery. It now selects those paths with `{{}}`, which evaluates independent reads concurrently and retains their source order. The reduction concatenates the completed lists; the existing global sort remains. The collection's keys, filtering and test batching keep their existing behavior.

The measured source is kept separately from the final formatter/comment-only cleanup in local commit `777aeb5`. Focused ownership and test-collection checks pass with fresh inputs, including host overlays, nested modules, Unicode and source order. The final source also passes the Dang v2 formatter. No new test duplicates those existing cases.

## Benchmark conditions and work

Every arm starts a fresh CLI and edits a Go source comment on a warm persistent engine. The source is dagger/dagger `ff0b029a`; the control Go module is `b5dd9434`. Telemetry and ordinary GC remain enabled. Both arms use declaration reuse, metadata batching, the selected attribute decoder and snapshot seeds. Callback caller reuse, flush coalescing and metadata read-ahead remain disabled. No engine cache is cleared and listing starts no compiler/test workloads. These measurements isolate the module patch on the existing experimental engine, rather than compare against stock upstream Dagger.

| Order | Serial discovery | Parallel discovery |
| --- | ---: | ---: |
| Before, after | 85.35 s | 72.37 s |
| After, before | 86.27 s | 70.11 s |

The first candidate performs 801 additional session flush requests: 2,565 versus the usual 1,764. Its module source identities are first used for the full repository in that arm; the following candidate returns to the usual count, consistent with initial cache population. The additional call classes were not profiled. Its cumulative allocation is 46.64 GB versus 43.71 GB for the first control. All attempts are retained. In the reverse comparison both have the usual 1,764 requests: allocations are 43.64 GB in both, engine CPU is 292.14 → 285.08 seconds, and sampled peak heap is recorded in the complete samples. The initial allocation increase does not establish a steady-state regression, and these pairs do not establish a general memory reduction.

A completed wcprof capture returns the same rows in 75.27 seconds, with 562,193 events, zero dropped events and no open operations. Compared with the preceding diagnostic, `Go.packages` decreases from 42.51 to 27.57 seconds. These are separately profiled runs, not a clean timing pair. They locate the shortened chain; concurrent child durations are not added to obtain command time. The remaining initial `Gomod.modules` discovery takes 9.90 seconds, while per-package test collection expansion still takes about 27 seconds. Sampled stacks do not show the previous long snapshot-GC root scan or metadata-update blockage.

The additional `isGoModule` selection passes five focused existing checks. Its first candidate performs 4,704 flush requests and takes 76.19 seconds, versus 2,565 and 72.89 seconds for the first control. In the reverse order, both perform the usual 1,764 requests and take 64.25 versus 72.35 seconds. Those initial population effects require a direct warmed confirmation.

## Direct confirmation of both changes

After both final source identities have completed full listings, two alternating orders compare original `b5dd9434` with combined `9eb4c36`. Each arm performs 1,764 session flushes, succeeds with identical 4,398 rows and starts a fresh CLI/source edit. The same engine settings and normal GC apply.

| Order | Original | Both selections |
| --- | ---: | ---: |
| Before, after | 88.39 s | 66.42 s |
| After, before | 88.90 s | 67.80 s |

Median latency is **88.65 → 67.11 seconds**, a 21.53-second gain on this experimental engine. Total engine CPU increases 299.21 → 309.40 seconds and allocations increase 43.84 → 44.28 GB. Sampled peak heap is 12.33 → 12.21 GB. Both orders are faster, but these observations do not establish a general CPU or memory reduction. Host I/O stall remains below 3.6%; maximum host CPU stall is 16.1% before and 22.5% after. Concurrent discovery increases overlap; no generic map/reduce semantics or engine locks change.

The two commits are `777aeb5` (package discovery) and `9eb4c36` (validity checks). The final formatted sources are preserved separately from the initial package-only measurement. The [combined PR description](PR_GO_PARALLEL_DISCOVERY.md) is ready; no PR is opened.

## Next engine investigation

In the root-selection profile, two goroutine samples show 794 and 767 requests waiting at `getOrInitClient`'s session lifecycle mutex. One active initialization reaches `Interface.FieldSpecs` while reconciling a fork's interfaces; the other sample reaches metadata cloning. These snapshots identify contention, not each operation's time share. Query-phase instrumentation begins after client initialization and therefore does not measure that lock wait. Schema-building after initialization totals only 1.24 seconds across queries and is a different phase.

The existing per-pass interface-field snapshot experiment is now measured on this larger case: two pairs improve median command time 69.15 → 67.76 seconds, CPU 311.83 → 300.27 seconds and allocations 44.28 → 43.31 GB. All commands return identical rows and exit successfully. Current ownership and actual test-collection checks pass with the option on. The option is restored off because the complete-command gain remains small and earlier smaller-workload measurements were mixed. [Complete observations](experiments/go-interface-snapshots-large/). Skipping reconciliation or releasing lifecycle locks needs a separate correctness argument, especially for changed views, dirty definitions, concurrent installation and teardown. No such change has been made.

[Source, commands, complete observations, correctness logs and profiles](experiments/go-parallel-package-discovery/). No PR is opened.
