# Native dependency objects expose repeated schema setup

The refined complete-command comparison improves **38.30 → 35.86 seconds**, faster in all four pairs, about **6.4%** by median. It combines ordinary `Gomod` object retention in the Go module, shared recovered schemas in the engine, and stable core-provider identity. An independent engine-only comparison on the unchanged selected Go module gives **37.41 → 37.67 seconds**, faster in only two of four pairs. The established gain concerns the combined prototype; there is no demonstrated generic engine speedup on the existing module. No new proposal or PR is added, and the experimental controls remain off between comparisons.

The earlier version establishes **no listing improvement**: **42.43 → 42.96 seconds**, faster in two of four pairs. It shares recovered schemas but lacks stable provider identity. It remains rejected; its component gain alone is insufficient.

All commands in both comparisons finish successfully with the correct ordered rows: 4,399 in each excluded initialization pair, then 4,398 in four fixed alternating pairs. Timing includes CLI exit, cleanup and a final log flush in both arms. Every invocation has a fresh CLI and source comment on the same retained volume. Telemetry and ordinary maintenance remain enabled. No observations are discarded. The rejected version increases median allocations from 30.76 to 32.69 GB and CPU from 201.20 to 219.95 CPU-seconds. The refined version increases allocations from 29.41 to 30.20 GB while CPU falls from 193.48 to 190.97 CPU-seconds. These separate cohorts are not additive gains.

## What works in isolation

Storing the library avoids repeatedly reconstructing the same dependency root. The first attempt cannot load: a constructor argument cannot reference a dependency's type. The revised prototype follows the existing package collection pattern, retaining its own `Go` tool object in each `GoModule`. All 24 existing Go development checks pass on the previous engine and again on the controlled candidate, including retained packages used with an edited module layout, custom bases, tests, builds and generation. The selected module is unchanged.

Native handles expose another path: loading them recovers the API schema of their defining modules. The existing memo is per client, so identical module sets can be installed repeatedly in internal clients. A real `Query.ModDepsForCall` regression reproduces eight installations on main and one with the fix, while all eight clients return their distinct constructor values. A second session builds independently. Shared templates retain no constructor arguments, host-history donor capabilities or cache-volume state. Each client receives its own schema fork and query root.

Four alternating component pairs prepare 64 fresh client roots with 128 functions:

| Per operation | Before | After |
| --- | ---: | ---: |
| Time | 12.88 ms | 1.36 ms |
| Allocated bytes | 11.83 MB | 1.94 MB |
| Allocations | 190,087 | 10,887 |

All four pairs improve. Each iteration creates fresh session and client memos; code is warm. These are component measurements, not full-command savings. Clean-main and exact-engine schema checks pass with the race detector. Neither memo's map lock is held during installation; the existing per-builder load lock still serializes construction.

## What the real repository adds

The first full prototype diagnostic returns the correct rows in 67.46 seconds but overflows wcprof: 286,978 events are dropped at its 4,194,304-event cap. It is retained and rejected for exact counts. It also overlaps 6.96 seconds of ordinary compaction. Its CPU samples identify substantial schema construction; its elapsed time is not a matched comparison.

The next capture drains the recorder every ten seconds and compresses the chunks after the command. It verifies the same recorder epoch and stable string-table prefixes. It records 2,744,897 events with zero dropped or open and exactly links all 8,621 SDK requests to their admission and query operations. The diagnostic command takes 47.36 seconds, including profiling overhead.

Against the earlier selected-module capture, library-constructor preparations fall from 4,333 to 396, but requests rise from 7,820 to 8,621. These are diagnostic counts from different engine binaries, not matched timing evidence. There are still 157,299 `Query.typeDef` operations. The complete unprofiled comparison above is the selection criterion and shows no gain.

The component fixture reuses one provider instance. The real server instead calls `CoreSchemaBase.CoreMod(view)` for each internal client; that getter creates a fresh immutable wrapper. The schema memo keys non-user providers by pointer, so equivalent core providers split the key space. A second regression reproduces this on main. Canonicalizing the wrapper for its exact base and API view passes concurrent lookup, distinct-base and distinct-view checks with the race detector. Receiver views remain unchanged.

The refined lossless capture returns all rows in 39.38 seconds with profiling. `Query.typeDef` operations fall from 157,299 to **8,406**, and total events from 2,744,897 to **1,060,564**, with zero dropped or open. It preserves exact request links and the same 8,621 SDK requests. These counts establish removed registration work; the unprofiled full-command pairs establish the latency result.

## Current boundary

Engines `8e90e469` and `5be8cc29` preserve the selected settings and cache volume through graceful restarts. With the candidate controls enabled, all six first calls reuse every retained Rust action: 130/130, 1,026/1,026 and 6/6, twice each. The six retained checks pass again after the refined comparison. All 24 existing Go development checks pass on both engines. These correctness checks establish retained-cache reuse, not a Rust latency gain.

The controls keep provider canonicalization separate from recovered-schema sharing. The first build catches a setup error: a full main file references `identifierSchema`, absent from the older engine base. That build is never installed. The corrected overlay applies only the identity changes to the actual engine source. Focused races pass with both controls off and on before replacement. The completed isolation comparison changes only those engine controls; its module, CLI and source are identical in both arms. All commands and cleanup pass, and source files, configuration, flags and profilers are restored. The existing module has no established gain, so the engine-only candidate is rejected.

The remaining diagnostic path contains 7.60 seconds of field preparation, 5.50 seconds around invocation, 3.05 seconds reading artifact dimension keys and 2.41 seconds in host directory imports. These mutually exclusive path intervals are not predicted removable savings. In particular, the Go library validates discovered modules by reading their `go.mod` files individually. Sharing a native marker snapshot is a concrete next experiment; malformed modules, nested modules and workspace overlays must keep their current behavior.

[Go prototype sources, all comparison rows and both profiler outcomes](experiments/go-stored-library-root/), [clean-main schema-sharing regression and component results](experiments/recovered-schema-templates/), and [provider-identity regression, controlled-engine checks and retained-cache proofs](experiments/recovered-schema-stable-core/) preserve all attempts. The completed earlier controls are [recorded separately](NATIVE_GO_SESSION_LOG_CONTROLS.md).
