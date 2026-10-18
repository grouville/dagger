# Recognize typed method declarations after type checking

Type checking wraps typed methods in a conversion node. The declaration classifier checks only for a directly held function, so it treats those methods as variables that need initialization. Rebuilding an object then allocates a deferred initializer for every method and immediately runs it just to create the function value.

Look through the conversion node when choosing the declaration phase. Evaluation keeps the original node, so type conversion, receivers and default arguments retain their existing behavior. This adds no cache, lock or public API.

This showed up while profiling Go test collections on dagger/dagger: expanding 800 package getters reconstructs 64,800 nested objects. On our development Dagger engine, complete listing after a real test-file edit improves **14.31 → 12.71 seconds**, faster in all four balanced pairs. Engine CPU falls **78.97 → 68.79 CPU-seconds** and allocation **17.40 → 16.62 GB**. A receiver-preparation fixture with 800 packages, 80 owners and 32 methods per owner improves **2.50 → 1.68 seconds**, with allocations **2.33 → 1.78 GB**.

Ordinary-source-edited listing does not improve: **6.75 → 6.90 seconds**, faster in one of four pairs. The change helps when collection receivers must be rebuilt. The complete-command comparison uses the same local engine binary and Go module in both arms, with a warm engine, fresh CLI processes, real edits, telemetry, ordinary GC and successful cleanup. It does not establish a stock-main Dagger speedup or cold-start performance.

The regression fails on clean upstream `da1bed304cb80f8a2f0714f1747e7f64e03297a3` and passes with the patch. It checks that a parsed, inferred method avoids variable initialization and still uses its current receiver and default argument. A second test covers a computed initializer calling a later method. The full upstream `./pkg/dang` race suite passes. Seven focused Go/library checks also pass, including collection test execution and module-boundary changes. All 20 complete listing commands return correct ordered rows and exit successfully.

The main behavior to review is declaration ordering: wrapped methods now enter the existing function phase before computed variables. Function bodies still run only when called, and their conversion wrappers remain intact.
