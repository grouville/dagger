# dagql: avoid temporary input copies when building schemas

When building argument definitions, DagQL first copies every selected InputSpec into a temporary slice, then reads that slice to construct the definitions. Most observed input-list allocation comes from this schema-building path.

Share the existing selection algorithm between callers, returning indices into the original specs. ArgumentDefinitions builds its output directly; Inputs still returns a separate list. View overrides, argument order, defaults, directives and validation remain the same. There is no new cache, lock or API.

Four alternating component pairs reduce allocation for eight definitions from **4,012 to 2,731 bytes** and time from **3.45 to 2.94 µs**. On complete dagger/dagger Go test listing after a test-file edit, the same warm experimental engine moves **6.76 → 6.58 s median**, allocating **6.313 → 6.114 GB**. All four pairs are faster, although paired savings range from 6 to 414 ms. Each command starts a fresh CLI and includes telemetry and cleanup. These are experimental-stack results, not cold-start or stock-release measurements.

The tradeoff is one extra temporary allocation for direct Inputs calls with more than 15 raw arguments. The 16-argument benchmark moves **1.712 → 1.767 µs**, adding 128 bytes. Source-edit listing has flat CPU and allocation; no general latency gain is claimed.

The full DagQL race suite passes on the standalone branch and development engine. Compatibility tests cover visibility, override precedence, metadata and output ownership. All 27 public Go checks, 28 Rust/native-cache cases and 24 timed listings pass with expected outcomes. Four lossless profiles retain all 800 getters, the same 804 module evaluations and 799 discovery hits.

[Source, complete measurements and limits](NATIVE_SCHEMA_ARGUMENT_ITERATION.md).
