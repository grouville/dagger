Title: fix: fingerprint package ownership by module boundaries

This refines our pending package-ownership prototype. Its guard hashes a sparse directory containing `go.mod` files. Converting a host workspace to a native test snapshot can change that fingerprint even though the module paths are identical, making every package rediscover its owner.

Fingerprint the sorted workspace-root-relative `go.mod` paths instead. Separate paths with NUL and hash the immutable record through the existing File API, excluding metadata. Added, removed or moved modules invalidate ownership. Source edits, file metadata and unrelated empty directories do not. Execution continues to read current Go versions and source contents.

The host/native regression fails before the patch and passes after it. Focused checks cover boundary changes, contents, permissions, cwd and retained-package rebinding. All 24 checks pass on the combined native-input prototype.

In a separate four-pair comparison on that prototype, with a real test-file edit in every invocation, complete listing improves **26.86 → 17.59 seconds median**, faster in every pair. CPU falls **148.25 → 89.09 CPU-seconds**, allocation **24.66 → 15.83 GB**. All listings have identical 4,398 rows and successful cleanup, with telemetry and ordinary GC enabled. Separate profiles verify **800 → 0** fallback lookups.

These are warm development-engine measurements against our earlier prototype, not stock upstream. This is a module guard correction; it does not establish an engine hashing bug. No PR is open. Full paired data and the remaining test-edit limitation are in `NATIVE_GO_NATIVE_TEST_DISCOVERY.md`.
