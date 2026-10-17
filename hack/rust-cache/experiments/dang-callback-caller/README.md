# Reuse the synthetic caller of Dang function callbacks

A diagnostic allocation profile of the full Go listing attributes about 2.3 GB to `NewType` under `callFunc`. The helper creates a temporary object and type, including nine empty maps, for every collection callback.

For concrete `FunctionValue` callbacks, `Call` only reads the synthetic caller's `self` and derives fresh locals from the function's closure. The prototype reuses that read-only, empty caller. Other implementations of `Callable` retain fresh mutable callers. This does not share argument maps or the function's local scope.

Concurrent argument isolation, captured self, custom mutable callables and the focused existing block/return/continue/self/closure race tests pass. The first captured-self fixture expected a bare field read to follow self updates; it returns 3 with both unchanged and modified code. Its failed control is retained. The corrected fixture reads `self.value` explicitly and passes.

Four alternating before/after benchmark orders measure 2,230 → 1,391.5 ns per callback, 2,648 → 1,464 allocated bytes and 30 → 17 allocations. This is a callback microbenchmark, not a measured complete-command gain. The opt-in engine comparison is now complete: median 83.77 → 82.22 seconds for the same 4,398 rows, with successful cleanup in all four commands. The diagnostic is disabled after measurement and no PR is opened. See [the full report](../../NATIVE_DANG_CALLBACK_CALLER.md) and [engine evidence](engine/).

The overlay targets the existing local Dang v2.1.4 source with earlier parser-cache changes. All benchmark output and focused tests are included; executable test binaries are omitted.
