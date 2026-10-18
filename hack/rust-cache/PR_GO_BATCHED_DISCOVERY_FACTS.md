Title: perf: batch Go discovery facts and reuse module owners

Listing Go tests repeatedly asks the shared library whether a module is selected and how to prefix its paths. Package discovery already knows the owning module, but later collection expansion reconstructs it.

Batch those immutable facts in the shared library and retain the discovered owners. Keep the existing layout-digest check, so packages still resolve their owner again when execution uses different module boundaries. Test names and source contents remain live workspace reads. Binary-directory selection uses the same existing policy in one bulk call.

On real `dagger/dagger`, listing all 4,398 test checks improves **25.45 → 19.21 seconds median**, faster in all four alternating pairs. Both arms use the same experimental engine and CLI; only the Go module differs. Each command uses a fresh CLI and source edit on a warm engine, with telemetry, ordinary GC and successful cleanup included. This is not a stock-main comparison or a cold-start result.

| Measure | Before | After |
| --- | ---: | ---: |
| Complete command | 25.45 s | 19.21 s |
| Engine CPU | 114.74 CPU-s | 93.28 CPU-s |
| Cumulative allocation | 18.01 GB | 17.13 GB |
| SDK requests, separate profile | 7,820 | 4,845 |

All measured listings have identical ordered rows. Adding a real test during initialization produces 4,399 rows in both arms; removing it restores 4,398. Allocation falls in all four pairs, CPU in three. All 24 Go-module checks and three targeted library checks pass, including overlays, nested module rebinding, binary selection and generation. Selection tests cover exclusions, normalization, Unicode, empty lists, duplicates and ordering.

This review branch is based on the existing package-ownership prototype at `7568cd0`; it still needs an upstream-base port. It adds no engine dependency or lock. Full evidence and exact paired timings are in `NATIVE_GO_BATCHED_DISCOVERY_FACTS.md`. Listing remains much slower than the three-second target.
