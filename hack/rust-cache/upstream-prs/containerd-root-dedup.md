# gc: visit each initial root once

**Draft under validation.** This is an additional containerd candidate, separate from the six prepared Dagger branches. The control slowdown below remains unresolved. No PR is open.

Containerd can discover the same snapshot through many leases. `Tricolor` adds every copy to its initial stack even though it already records the roots in `seen`. It therefore loads a shared root's references repeatedly. A retained Dagger cache has 399,795 roots for 77,784 distinct nodes; one root appears 18,418 times.

Queue each exact root once, using the existing `seen` map. Keep the full resource type, including traversal flags, and the namespace when comparing roots. This preserves different reference traversals and the final live set. The change adds no lock, persistent state or API, and leaves collection scheduling unchanged.

Marking a read-only copy of that cache gives:

| Mark phase | Before | After |
| --- | ---: | ---: |
| Time | 878 ms | 528 ms |
| Allocated bytes | 442.7 MB | 274.0 MB |
| Allocations | 7.68 million | 2.92 million |

Six alternating fresh-process pairs, Go 1.26.6, linux/amd64, `GOMAXPROCS=8`. All six improve and preserve the same 77,772 canonical live nodes, checked against an independent traversal. Database opening and fixture validation are outside the timer. These timings exclude sweep and physical deletion.

The extra membership check has a cost when every root is distinct: 1,000 roots with no outgoing references take **263 → 287 µs**, about 9% slower, with unchanged allocations. A one-root control shows similar timing and allocations.

This work can block foreground operations: profiles show Dagger host imports waiting to create leases while containerd holds the metadata collection lock. In two eight-pair command cohorts, edited checks of a 1,026-crate Rust workspace during concurrent collection take **2.438 → 2.170 s** and **2.381 → 2.042 s**. All sixteen pairs improve. The confirmation deletes only a one-file scratch snapshot. Engine and compiler caches are warm, processes are fresh, and telemetry remains enabled. The comparison forces collection to overlap the command; it does not measure how often production collection runs.

Without concurrent collection, the first cohort is mixed, but the confirmation takes **1.482 → 1.535 s**, with all eight candidate observations slower. The median paired penalty is 62 ms. Preparation and cleanup still use the selected collector, so this does not isolate the cause. The slowdown needs explanation before submission; no ordinary edited-command benefit is claimed.

The regression combines duplicate roots, a cycle, namespaces and traversal flags. It checks the complete retained set, one reference lookup per distinct node, and unchanged input roots. Against containerd main `c787e39387ec`, it fails before the patch; the GC race suite and `go vet` pass afterward with Go 1.27.0, with no skips. GC and metadata race suites also pass on Dagger's v2.2.5 dependency. The real Rust module passes cold compilation, reuse, source edits, a deliberate compiler error, repair and reversion, with actual collection after every phase.

Repository-wide lint remains unrun because `golangci-lint` is unavailable. [Standalone patch, raw measurements and validation logs](../experiments/containerd-root-dedup/) and [experiment details](../NATIVE_GC_ROOTS.md) are available for review. The large raw metadata database and executable binaries are excluded.

AI assistance was used to prepare this change and its measurements. Human review is pending.

The [subsequent investigation](../NATIVE_GC_ROOTS_FOLLOWUP.md) separates the idle penalty's preparation effect from the command-only flag and tests a single-lookup alternative. That alternative preserves all six retained compiler histories. Its ordinary-command comparison is unchanged at about 1.55 s versus Cargo's 0.77 s; its concurrent-collection comparison improves in six of eight pairs. Those are separate measurements of a different loop, and do not replace this draft's original results or resolve every latency effect.
