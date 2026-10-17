# Configuration declaration reuse

The [measurement report](../../NATIVE_CONFIG_DECLARATION_REUSE.md) and [PR description](../../PR_ENGINE_CONFIG_DECLARATIONS.md) explain the change and tradeoffs.

- [Standalone patch](evidence/testdata/standalone.patch) and [upstream-based validation](evidence/testdata/standalone-validation.json).
- [Complete listing results](evidence/testdata/full-command-paired/summary.json), raw outputs and paired pressure observations.
- [Component results](evidence/testdata/components/summary.json), including the initial miss penalty, isolated repeats and CPU captures.
- [Wcprof critical path](evidence/testdata/capture/main-critical.txt), CPU/allocation reports and compressed raw captures.
- [Final selected state](evidence/testdata/selected-state.json) and native compiler-cache checks before/after restart and after listing/profiling.

The manifests verify captured files, decompressed contents and inherited sources from preceding sibling archives. Three executables are omitted; their identities and build commands remain available. The standalone branch is pushed for review. No PR was opened.
