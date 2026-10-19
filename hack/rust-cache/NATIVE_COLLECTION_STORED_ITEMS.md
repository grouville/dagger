# Stored collection items remove getter runtime setup

A native stored-item prototype improves complete Go test listing after a test-file edit **10.81 → 7.04 seconds median**, faster in all four balanced pairs. Engine CPU falls **57.51 → 27.67 CPU-seconds**, and cumulative allocation **15.25 → 6.69 GB**. It remains a prototype: ordinary-source listing regresses **6.00 → 6.52 seconds**, slower in all four pairs. Cold-start effects are not measured, and three seconds remains unachieved.

| Complete-command workload | Function getters | Stored items |
| --- | ---: | ---: |
| Test-file edit | 10.81 s | 7.04 s |
| Ordinary-source edit | 6.00 s | 6.52 s |
| Test-file edit, engine CPU | 57.51 CPU-s | 27.67 CPU-s |
| Test-file edit, allocation | 15.25 GB | 6.69 GB |

The median paired test-edit saving is 3.70 seconds; the source-edit regression is 0.52 seconds. These are real edits with a fresh CLI on a warmed, independent development engine. Telemetry, ordinary GC, command exit, cleanup and final log flushing are included. Both versions finish the test-addition/removal transition before four measured pairs per workload. All **24 commands** exit successfully and return the correct ordered names and full rows: 4,399 during initialization's addition and 4,398 afterward. No profiler, build or check runs alongside timings. This comparison is not stock released Dagger and is not an additive gain against previous cohorts.

## Change

The existing `@get` marker can point to a stored list of entry objects, each with a required `key` and object `value`. A function getter keeps its existing behavior. A stored getter is an explicit choice; the engine does not inspect or bypass an authored getter's body.

The engine validates the entry signature, indexes entries by their own key, checks the collection's current selected keys, and returns the item through normal module type conversion. The index belongs to an immutable collection value, holds no context or client, is rebuilt after decoding and is replaced for subsets. Item content identity keeps module implementation, return type and effective view in its scope. This uses ordinary Dagger objects and native filesystem snapshots, without a cache volume or separate result store.

The Go variant constructs package entries while each module's owner is already known. It removes repeated owner searches and the per-package module getter. The keys, nested test collections, source overrides, selection, binary and generation operations keep their existing behavior in the focused checks. The prototype requires its matching engine and is not a drop-in upstream module change.

SDKs normally emit named type references without their fields. The first real-module attempt therefore failed entry-signature validation. The Dang prototype now includes only the entry's key/value field signatures in that reference; item types remain nominal references, avoiding recursive definitions. This uses the existing builder API, with no new directive name or generated-client method. Equivalent SDK support and documentation remain work.

## Evidence and limits

Separate lossless wcprof captures show **804 → 4 module evaluations**, while SDK requests stay **1,494 → 1,493**. All 800 collection gets still happen through the engine; the candidate resolves them from stored data. Both captures execute one changed test discovery and reuse 799 unchanged ones. Thus the gain comes from removing complete runtime setup cycles, not reducing query count or freezing names.

In the candidate's 7.02-second profiled main query, shared `Go.packages` discovery takes about **5.92 seconds**. The module still serializes 800 directory IDs. Constructing and serializing stored entries adds work to the ordinary-source path, where the old getters already hit. The next experiment must address that preparation and transfer without weakening source freshness or per-item reuse.

The core race checks cover concurrent lookups against reversed entry order, subset access, unchanged versus changed item reuse, module implementations, return types and effective views. Existing object ownership/persistence and SDK race checks pass. Eight module commands pass, including custom base images and Go flags, root/nested test execution and exclusions, native test snapshots, source overrides, edits, module-boundary changes, collection execution, binaries and generation.

This is not yet a complete feature validation. Malformed entry data, additional scalar/enum key cases, stored-entry-specific persistence and resource lifetimes, imported collections and all SDK registration paths need further coverage. The design and code size also need review before any upstream proposal. The source-edit regression prevents selecting it as the default.

## Reproduce and review

Go branch `grouville/go:experiment/native-collection-items`, commit `545b957b0d86964426aa6e8051e8ec751f670a1f`, has parent `a3d0e4bf562b834c31135bff24e5931fd32b3acc`. Both arms use engine `71fb69deb9262822ac5d989536000fb6176b9cfaa29b0143e4e4eaa5141f86fd` and CLI `97f7d82dc2f7b3da203aa683971ea3658b6de6a8e9b968a44905e379f499f965`. The engine runs as `dagger-collection-native-items-oct18` on runner 16279/debug 16107, with its own cache volume. Existing Go and Rust engines and their volumes are unchanged. Temporary profiling and benchmark switches are restored.

[Minimal prototype patches and all evidence](experiments/native-collection-items/), [review notes](PR_NATIVE_COLLECTION_STORED_ITEMS.md). No PR is opened. The Rust module/cache integration remains unfinished.
