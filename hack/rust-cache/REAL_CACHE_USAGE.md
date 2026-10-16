# Cache accounting on retained Rust histories

The existing [usage-map proposal](upstream-prs/cache-usage-maps.md) also improves accounting on the actual Rust benchmark engine. Preparing a prune state takes 563 → 538 ms in one series and 567 → 530 ms in a reversed-order confirmation. Both series contain eight pairs; 13/16 pairs improve. This is preparation for pruning, not a complete Rust command or an engine restart.

The same process retains 59,192 results and accounts for exactly 32,207,045,457 bytes throughout both series. Each measurement calls the existing `measurePruneState`, including size measurement and disk-prune snapshot construction. It does not plan or execute evictions.

| Per preparation | First series, before → after | Confirmation, before → after |
| --- | ---: | ---: |
| Median elapsed time | 562.83 → 537.58 ms | 567.46 → 530.24 ms |
| Median paired saving | 27.46 ms | 45.71 ms |
| Faster pairs | 7/8 | 6/8 |
| Allocated bytes, median | 219.63 → 205.24 MB | 219.58 → 205.37 MB |
| Allocations, median | 1,298,000 → 995,809 | 1,297,997 → 995,823 |

Allocated bytes fall by about 14.4 MB and allocation counts by about 302,000 per preparation in both series. Every pair allocates less. Process-wide counters include concurrent engine activity; these are observations on this retained cache, not a fixed saving per arbitrary cache entry.

CPU totals are mixed. The first series samples a Go garbage collection during one candidate observation and none during the baseline observations: summed engine CPU is 4.53 → 5.86 seconds. The confirmation samples one collection in each arm: 6.18 → 6.07 seconds. All observations remain included. Median CPU falls in both series, but this experiment does not establish lower total CPU consumption.

## Method and correctness

A diagnostic-only overlay adds a switch around the existing map change and an HTTP measurement endpoint. Both modes run in one engine process and use the same cache population. The endpoint serializes with existing GC, temporarily selects the implementation, measures it, and restores the previous mode. The upstream patch has no switch, endpoint, counter or additional lock.

Two preparation pairs precede each series. Subsequent launches require no active session and a one-second window below 5% host and 1% engine I/O pressure. Profiling is off. Maximum host I/O pressure during measured calls is 4.26% in the first series and 3.91% in the confirmation; engine I/O pressure is zero. No slow observation is excluded.

The diagnostic binary is `f61dfab5738e8f074c805da62a9e1224eebaf448f59c16399bf1953a6278eb04`, built from the preceding experimental engine and its pinned overlays. Installation preserves the existing volume after a graceful exit. The 169.588-second shutdown and cache restoration are outside the comparisons. This does not compare two isolated upstream-main engine builds.

The dagql race suite passes with the change enabled, excluding one existing diagnostic incompatibility: `TestSyncResultSnapshotLeasesRecordsLockWait` expects a lock name without the instance suffix added by our wcprof overlay. Its identical failure with the change disabled is archived. The standalone upstream branch's full race suite already passes without that overlay.

After the restart and measurements, all eight native histories reuse every compiler result: two each with 130, 1,026, 6 and 512 actions. Previous batch markers also remain intact. No new production tests are needed for the allocation change; the existing ownership, cancellation and cleanup tests cover its behavior.

The result supports the small upstream change, while keeping its benefit in proportion: tens of milliseconds per accounting preparation on this cache. It does not establish a faster complete Rust build. Automatic session GC is throttled to once per minute in this engine, with separate pressure and shutdown triggers, so this cost is not paid after every command.

[Raw observations, source overlays, exact build inputs and validation logs](experiments/usage-maps-real-engine/) are archived. The owned engine keeps the diagnostic binary with the original allocation behavior selected outside measurement calls. The full Rust performance roadmap remains active.
