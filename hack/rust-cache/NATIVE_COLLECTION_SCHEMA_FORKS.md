# Follow the module API waits

The last validated complete Go listing remains **39.20 seconds median** for all 4,398 tests, including successful cleanup. It uses fresh CLI processes and source edits on a warm retained engine, with normal telemetry and garbage collection. The [scalar getter comparison](NATIVE_COLLECTION_SCALAR_PROJECTION.md) establishes that result. This investigation adds no complete-command improvement.

Collection UX remains the requirement. A different engine implementation is in scope when it preserves selection, IDs, ownership and native cache behavior.

## Where the API requests wait

The completed 39.98-second diagnostic has 509,170 wcprof events, none dropped or open. Its main query spends 27.41 seconds inside synchronous module API requests. Those intervals include engine work and waiting; they do not measure network or parsing cost alone.

Following the nested-client links identifies two requests whose backend query starts much later than the request:

| API operation | Complete request | Client admission | Backend query |
| --- | ---: | ---: | ---: |
| 119857 | 640 ms | 634 ms | 4.6 ms |
| 129835 | 2.818 s | 2.636 s | 177 ms |

An aligned goroutine dump shows a client initializer in interface inference, inside `initializeClientRuntime`, while other client admissions wait on session lifecycle serialization. This identifies a setup bottleneck. It does not establish that removing inference would save the entire admission interval: contention and overlapping work need a controlled comparison.

`Class.ForkObjectType` already clones installed interface membership. `Server.Fork` nevertheless marks every clone for a complete inference pass. That pass considers object/interface pairs again. Reusing a prepared schema could remove repeated work across many clients and benefit modules beyond Go.

Another large request spends most of its path in 162 nested API calls from `GomodGoMod.ownFiles`. The earlier shared-workspace-path experiment already reduces those calls without a demonstrated full-command gain. Likewise, parallel admission already has a mixed complete-command result. These findings do not justify repeating either unchanged experiment.

## Why the simple reuse prototype is rejected

Focused tests run against unchanged upstream `ff0b029a` and virtual source overlays, sequentially with the race detector:

| Variant | Counterexample |
| --- | --- |
| Carry the source's clean flag | Changing the API view loses newly valid relationships. |
| Track the API view too | Direct field installation and extension do not invalidate inference. |
| Invalidate after field changes | A concurrent clone can copy the new field but keep stale relationships. |

The third variant passes the initial focused race checks, including field changes, setup hooks and parent/fork isolation. A further controlled concurrent-update test passes on unchanged code and fails on the prototype. A wrapper arranges a field update before cloning that class. It waits only for the field to become observable, not for the updater to finish. Both versions copy the new field, but only unchanged code infers its relationship. Both updater goroutines are joined after cloning.

The clone holds the source server's read lock; the field updater has released the field lock but waits for the server's write lock to mark inference dirty. The clone can therefore inherit the old clean flag and copy the new fields. Merely marking the source dirty at the end of the update does not invalidate this clone. A separate callback-completion test also exposes a lock cycle when a custom fork callback waits for the entire update. That is an extensibility counterexample, not a demonstrated hang in today's production `Class` cloning path. No engine or subprocess is terminated.

A safe design must make the cloned fields and inference state agree even when updates overlap. It must also preserve invalidation performed by setup hooks, rather than overwriting it at the end of cloning.

The prototype is **unselected**. Its component binaries were built but never benchmarked after this counterexample was identified. A controlled engine overlay and comparison driver were prepared, but that engine was never built or installed and no full-command cohort ran. The selected engine binary, cache volume and Rust timing manifest remain unchanged. There is no new upstream proposal or PR.

## Next implementation choice

Evaluate an immutable prepared schema shared by clients, with independently owned client roots and schema extensions. Alternatively, use complete version tracking that makes reuse and invalidation safe across schema mutations. Either approach needs an explicit rule for fields, interface declarations, API views and cloning under concurrent updates. Avoid adding a blocking server lock from a field mutation.

First measure the cost removed on a representative prepared schema. Only then compare the complete listing in alternating pairs, with identical rows, successful cleanup and the retained native-cache checks. Artifact metadata still accounts for roughly nine seconds of the current path and remains a separate target for bulk projection that preserves object ownership and addressability.

[Evidence](experiments/schema-fork-reuse/) retains the request attribution, source variants, focused checks and counterexamples. Earlier trace captures remain in the scalar getter archive.
