# dagql: share class definitions until a fork mutates

Class forks eagerly copy all field maps, declaration-order slices and interface maps, even when the fork only reads them. Collection expansion repeats that preparation for many private clients.

Give each fork a private state record and lock while sharing its immutable definition storage. Before changing a field or interface, detach the maps and order under the branch's write lock. Ordinary value copies still share their branch's state. Client execution state, schema emission, getters and validation remain unchanged. This is based on the separate field-history isolation fix.

Against that fixed baseline, a read-only fork with 128 added fields moves **4.11 µs → 105 ns**, allocating **13,448 → 128 bytes**, faster in all four component pairs. A fork followed by mutation is broadly flat and allocates 24 bytes more. The implementation adds a storage indirection and an ownership invariant for mutators.

Complete test-edited Go listing has a modest, variable result. The initial cohort moves **7.66 → 6.91 s**, but is faster in only two of four pairs under substantial host contention. A separately admitted quieter cohort moves **6.74 → 6.55 s**, faster in three of four pairs. Allocation is lower in all eight test-edit pairs, saving roughly **202–239 MB** by the cohorts' median paired differences. Source-edit listing remains mixed. Both modes use the same experimental layout and engine; these are warmed development-stack results, not stock-release, cold-start or Rust latency claims.

Both standalone full DagQL race suites and the exact development-engine full DagQL race suite pass. All 27 Go checks, 28 Rust/native-cache cases and 48 timed invocations have expected outcomes. Four lossless profiles retain all 800 getters and the same discovery reuse. Tests cover nested forks, value copies, interface isolation, concurrent writes and override histories.

The allocation improvement is consistent; the end-to-end latency evidence is limited. Keep this as an experimental review candidate rather than an order-of-magnitude collection-listing claim.

[Complete measurements and source](NATIVE_CLASS_FORK_COW.md).
