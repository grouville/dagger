# Cold metadata scans block Go collection discovery

The first large opportunity is in snapshot garbage collection. On a consistent copy of the engine's metadata database, a cold root scan takes 72.78 seconds. Reading the database sequentially before scanning reduces that to 3.04 seconds, including the read. Both comparisons preserve exactly the same ordered 1,468,205 roots. This is a component result; a faster complete Go listing has not yet been demonstrated.

## Evidence from the running engine

The new full-repository diagnostics both succeed and return the same 4,398 checks. They take 198.14 and 118.89 seconds, respectively, and each wcprof capture contains 567,986 events with no dropped events or unfinished operations. These are diagnostics, with short CPU captures and sparse goroutine samples, rather than clean timings.

The slower diagnostic shows a root scan holding containerd's metadata write lock while imports and snapshot lease updates wait behind it. The engine accumulates roughly 370,000 major page faults over the scan interval. The earlier engine log independently reports 61.41 seconds in containerd's metadata phase, followed by 2.95 seconds of snapshot cleanup. The metadata phase includes marking and sweeping as well as root enumeration; it is not all root enumeration.

The faster diagnostic was intended to test read-ahead, but its trigger never observed a root scan and performed no intervention. Its shorter duration is not an optimization gain. A warm engine does not guarantee that its metadata pages remain in the operating system's file cache.

This is the live `github.com/containerd/containerd/v2/core/metadata` path, visible in both goroutine and CPU profiles. It is separate from the unused `internal/buildkit/cache/contenthash` package involved in the earlier rejected fix.

## Isolating the I/O cost

The fixture is a 1,527,734,272-byte copy of the owned engine's `containerdmeta.db`. Both transaction metadata pages remain identical before and after copying, and the copied database passes bbolt's full integrity check. The benchmark uses the engine's exact bbolt revision, eight Go processors, a read-only transaction, and the same scanner in both arms.

Two comparisons run in opposite orders. Before each cold process, file-specific advice evicts only this private copy's file cache. `mincore` verifies zero resident pages. The live engine database, its native snapshots and its retention policies are untouched. Every process verifies the full ordered-root digest against the integrity-checked oracle after timing.

| Cold root enumeration | Median | Major page faults |
| --- | ---: | ---: |
| Existing scanner | 72.78 s | 355,634 |
| Sequential read, then existing scanner | 3.04 s | 0 |

Sequential reading issues about 4.2% more disk I/O on this fixture. Its speed comes from changing the access pattern, without removing roots or delaying collection. When the file cache is warm, however, the full read adds approximately 156–332 ms across separate two-pair diagnostics. That motivates testing advisory read-ahead instead of copying the entire file through userspace.

One-megabyte hints are insufficient on this machine: its devices advertise a 128 KiB read-ahead window. They reduce cold enumeration only from 75.16 to 66.05 seconds and leave about 311,129 major page faults. Two opposite-order comparisons with contiguous 64 KiB hints give a cold median of **74.17 → 2.37 seconds**, with major faults falling from 355,611 to zero. Every run still produces the identical ordered root digest. In the same cohort, warm-file-cache medians are **1.49 → 1.53 seconds**, approximately 37 ms extra. There are only two pairs, so this is not a precise estimate of a fixed warm overhead.

## Scope of the prototype

The engine-only prototype issues advisory reads before containerd acquires its metadata write lock. It retains the existing traversal, leases, locks, cache identities and collection policy. Advisory failures fall back to normal collection. Hinting precedes clearing the existing pending-deletions flag, so deletions during preparation are covered by the subsequent collection.

The new diagnostic switch defaults off. Focused engine race tests pass with hinting enabled, including retained/released snapshots and successful cleanup when advisory preparation cannot open its file. The owned engine is being replaced gracefully, with all six existing native Rust cache histories checked before and after. A complete Go comparison remains required before claiming a command improvement. A database with many free pages also needs assessment: reading by file extent can request more data than the live metadata traversal needs.

Removing a separate per-root producer/consumer handoff improves a warm enumeration benchmark from 1.28 to 0.77 seconds, with identical ordered roots and passing metadata/GC race suites. It does not explain the minute-long cold stall and is kept separate from the I/O prototype.
