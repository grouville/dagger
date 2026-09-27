# Address-only engine for a module-owned base-address experiment

One engine was built successfully from the frozen ec6 behavior and current checkout revision 2088d5ef. It adds the focused UserDefault Address correction and the common, opt-in `artifact.moduleTree` / `artifact.coreTree` wcprof boundaries. Both module variants will use exactly this engine. No pruning, shared transport, split-init or newly extracted helper is layered in. The existing clean baseline is provenance, not a timing control.

The actual version is `v1.0.0-beta.15+2088d5ef.dirty`: the checkout had only documented `hack/` evidence changes. The build records its effective overlay/dependency hashes and VCS state; no source or version stamp was rewritten. The module and later runtime were not part of the engine build.

The earlier offline normal/race/default-resolution gates are in the separate source evidence snapshot. A final parser-only run also accepted the independently pinned producer fixture with separate source/service markers, SHA 3e4bc36c789a2a2413d602d8fa76f8fb87370c02dbf80446e8c1225c3f27a683. No engine or Cloud invocation was made here; actual module/service/cache/freshness validation and latency measurements remain pending. Compilation durations are not command performance.

Raw compiler/test logs and the engine binary remain private in the lab. The recipe identifies the pre-existing frozen source stack; this snapshot includes only the two new production overlays rather than duplicating that archived stack.
