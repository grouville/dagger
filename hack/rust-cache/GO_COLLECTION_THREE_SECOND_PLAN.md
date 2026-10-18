# Three-second Go collection listing

The goal is complete listing on the real dagger/dagger repository after an edit, with a fresh CLI, correct current-source rows, normal telemetry and successful session cleanup. Report ordinary-source edits and test-file edits separately. An engine restart and first discovery are distinct cold scenarios; a warm result does not establish either.

The latest useful prototype reaches 9.30 seconds after ordinary-source edits, but test-file edits remain mixed at about 20 seconds. Three seconds is unachieved. The subsequent package-snapshot prototype is rejected after 18.60 → 55.76 seconds. See [the complete comparison and profile](NATIVE_GO_PACKAGE_TEST_SNAPSHOTS.md).

## Working hypothesis

The order-of-magnitude opportunity is less work after an edit. A collection with 800 packages should not rediscover all 800 when one package's test file changes. Returning 4,398 rows still requires reading and formatting those rows; repeated discovery and module setup are additional costs.

A frozen-name control completes in 1.07 seconds with ordinary nested collections and full command cleanup. It provides evidence that traversal alone does not require 30 seconds on this stack. It does not prove that real discovery fits the remaining time.

## Sequence

1. Prove stable identity propagation in a small engine test. Change the parent collection while keeping one child's content unchanged. Its downstream function should reuse the existing result. Changed content must miss. Verify provenance, views and session resources as well as values.
2. Give child discovery only the native immutable source it needs. Avoid hundreds of snapshot rebuilds and repeated module-layout walks. Check the actual getter and discovery counts; a filtered file set is not proof of reuse.
3. Use wcprof on the complete command to choose the next remaining cost. Reduce repeated module/client setup, query round trips and lock contention where they lie on the critical path. Batch metadata through ordinary Dagger APIs while retaining per-test collection selection and execution.
4. Measure balanced before/after pairs on fresh real edits. Keep all attempts, compare exact rows and successful exits, and reject a component improvement that fails to improve the full command. Rerun broader correctness checks only for candidates that survive this screen.

## Acceptance

A change to one existing test file should refresh only necessary discovery, plus shared root work. Adding or removing a test must add or remove exactly its row. Adding, removing or moving `go.mod` must refresh package ownership. Explicit source overrides, overlays and object fields used as collection dimensions must continue to work.

The final claim must include total time, cold/warm conditions, CPU, allocation and the relevant source/binary identities. Compare fresh-edit scaling at different package counts before calling the approach generally efficient. Do not extrapolate a 10× claim from one component benchmark or add unrelated cohort gains.
