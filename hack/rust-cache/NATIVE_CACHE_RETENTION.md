# Native cache retention after edits

The automatic native-cache prototype exposed two retention problems. Module
objects can form parent/child ownership cycles on current upstream main; a
standalone fix now passes a regression and the actual Rust pruning study.
Separately, the latest retained incremental state still carries older snapshot
recipes. That history remains unbounded by the prototype's 128-key limit.

## A module-object lifetime bug

When a module returns `Compilation { cache: { ... } }`, attachment creates a
result for the inline `cache` object. The compilation owns that child result,
and the child's ordinary `Compilation.cache` receiver dependency owns the
compilation. Neither ownership count reaches zero after the session releases
them. Removing the native cache hint does not break this cycle.

The isolated retention engine confirms that its hint index was evicted: 128
distinct keys hold only an empty Directory. With no remaining sessions or
offers, the compiler objects have no external ownership roots. Their parent
and child references keep them alive through full pruning.

| After hint eviction and full prune | Control | Fixed engine |
| --- | ---: | ---: |
| RustCompilerCompilation objects | 32 | 0 |
| RustCompilerCache objects | 32 | 0 |
| RustNativeCompilation objects | 32 | 0 |
| RustNativeCache objects | 32 | 0 |
| Mutual parent/child ownership pairs | 64 | 0 |

The control has more preparation commands than the fixed engine. This table
demonstrates reclamation, rather than an equal-history size comparison.

The fix walks inline fields and directly retains their resource handles. It
keeps their SDK map representation and creates no separately owned child result
during attachment. Selecting that field later creates an ordinary result that
retains its parent, without a reverse edge. Existing object handles retain their
ordinary ownership. No cache inputs, locks or snapshot-lifetime checks are
removed.

The standalone regression uses current upstream main `2bbaf3deef`. It selects
an inline child, retains it across session release, reads its resource in a new
session, then releases the final owner and checks that parent, child and resource
are gone. It includes inline object lists and nullable fields. Main fails at
final reclamation; the fix passes. Focused module-object, SDK conversion,
persistence and collection checks pass under the race detector.

Standalone branch: [fix/embedded-module-cache-lifetime](https://github.com/grouville/dagger/tree/fix/embedded-module-cache-lifetime).
The first commit adds the failing regression to main; the second fixes attachment
and updates the existing inline-map test's ownership expectation.

An older closed [PR #14269](https://github.com/dagger/dagger/pull/14269) addressed
this class of cycle through a new recipe-reference policy. This experiment
changes the inline-object attachment boundary without adding that policy.

## The latest seed still retains history

The fixed engine performs 20 fresh app edits in the four-crate fixture. Each
edit reuses three compiler actions. Checks after each prune reuse all four.
The study waits for every CLI session to release before capturing the graph.

| Fixed engine, after pruning | Initial | After 20 edits |
| --- | ---: | ---: |
| Results reachable from the latest cache | 285 | 552 |
| Distinct snapshot references in that closure | 51 | 273 |
| RustCompilerCompilation objects in the engine | 1 | 1 |
| Mutual ownership pairs | 0 | 0 |

After the first checkpoint, each app edit adds approximately 13 results and 11
snapshot references to the retained closure. Pruning preserves those results
because the latest seed still references older Directory and Container recipes.
Fixing the object cycle permits eventual reclamation but does not compact this
live ancestry. A safe compaction must independently own the current native
snapshot and its resources, while retaining the seed as an ordinary explicit
compiler input.

The fixed engine's cache accounting falls from 3,933,591,863 bytes to 4,096 bytes
after hint eviction and pruning. This includes toolchain images and helper
snapshots; it is not a measurement of unique Rust incremental bytes. Whole-engine
disk occupancy afterward is 326,260 KiB, including telemetry and metadata. Cache
accounting and filesystem occupancy measure different things.

Artifacts are under `/tmp/rust-cache-sipsma-review/native-hint-retention` and
`native-hint-inline-retention`. The latter is a fresh candidate engine, with the
same Rust module, runtime and init assets as the control. Local telemetry remains
enabled. This study establishes correctness and reclamation, not a complete
edited-command latency improvement.

The actual Rust module also passes cold/edit/revert and normal check validation,
configuration recapture, new-target handling and unsupported-input rejection.
Its exported native cache fields produce 4/4 hits on a fresh receiver engine,
then 3/4 after a new source edit. The receiver's first attempt stopped during Go
module bootstrap because its DNS daemon exhausted the host's inotify instances.
Two idle benchmark engines were stopped, their volumes retained, and the DNS
daemon restarted. The successful repeat used the same receiver; its failed
attempt had imported no Rust compiler state.

Transfer logs are `inline-retention-transfer-{writer,reader,reader-retry}.log`
under the review directory. The native-cache validation engine branch is
[experiment/native-cache-inline-retention](https://github.com/grouville/dagger/tree/experiment/native-cache-inline-retention).
