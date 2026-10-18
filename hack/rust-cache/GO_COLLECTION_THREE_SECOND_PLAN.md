# Three-second Go collection listing

The goal is complete listing on the real dagger/dagger repository after an edit, with a fresh CLI, correct current-source rows, normal telemetry and successful session cleanup. Report ordinary-source edits and test-file edits separately. An engine restart and first discovery are distinct cold scenarios; a warm result does not establish either.

The latest candidate improves test-file-edited listing **14.31 → 12.71 seconds**, faster in all four pairs, by recognizing typed method declarations correctly after type checking. Ordinary-source edits show no gain: **6.75 → 6.90 seconds**, faster in one pair. The minimal fix and regressions also pass on a clean current upstream Dang snapshot. It remains available for review with its diagnostic switch disabled. [Complete comparison, source and scope](NATIVE_DANG_COERCED_METHOD_HOISTING.md). Three seconds remains unachieved.

These are fresh CLI processes and real edits on a warm isolated engine. Earlier cohorts used different engine/cache states; their latency differences must not be counted as additional gains. The preceding context-lookup candidate remains rejected: its component benchmark improves but its complete command does not. [Context experiment](NATIVE_DANG_EVALUATION_CONTEXT.md).

## Approach to a tenfold improvement

Start with the amount of work, its growth with repository size and its position on the critical path. The current listing performs 804 module evaluations and 2,293 nested SDK requests despite reusing 799 of 800 test discoveries. A tenfold gain needs much less repeated setup and conversion. A cheaper operation inside every evaluation is insufficient unless it materially reduces the complete command.

Receiver preparation is now measured: 800 getters process 79.6 MB of parent JSON, 1.87 million values and 64,800 nested objects. A method-heavy scaling fixture confirms substantial repeated allocation. Profiling led to a narrow first fix: typed methods were entering deferred variable initialization. Recognizing their conversion wrappers reduces sampled CPU under parent conversion from 13.52 to 7.92 CPU-seconds, with the complete-command benefit above. The same 804 evaluations and 2,293 SDK requests remain.

The larger experiment is still sharing immutable receiver preparation or evaluating items in bounded batches. Preserve per-key results, fresh mutable receiver state and normal collection selection. Measure bytes, allocations and elapsed time at increasing package and owner counts; conversion CPU alone is not proof of a latency gain. A new public API is justified only if existing boundaries cannot safely support the improvement.

One narrower next screen follows directly from the remaining CPU profile. `EvalNode` fetches the current source-error context and republishes the same value before evaluating every node. The candidate profile attributes 8.60 CPU-seconds to `GetEvalContext`. `WithEvalErrorHandling` already waits until an error before reading that state. Test whether node dispatch can likewise defer the read until it needs to wrap an error, preserving source locations, control-flow sentinels and the explicit `EvalNodeWithContext(..., nil)` behavior. Exact compiled source is archived under `next-target-source/`. This is a new work-elimination experiment, not a rerun of the rejected custom-context wrapper; no gain is established yet.

The second target is the repeated engine work around those calls. The latest candidate capture places 2.88 seconds of session lifecycle lock waits on its 12.75-second main-query critical path. Earlier parallel admission did not establish a complete-command win. Identify what the lock protects and how repeated calls cause contention before changing its scope. Shared preparation must preserve module/schema/view identity, resource ownership and cancellation, with a fresh invocation state for mutation. Do not reuse a creating session or cache live configuration by time.

Use **one second for discovery, one second for collection expansion and one second for CLI startup, source import, output and cleanup combined** as an initial three-second budget. These are design targets, not measured phase durations or promised gains. Replace them with measured sub-budgets as the complete command changes. Root discovery is itself about six seconds in the latest profile, so improving only getter execution cannot reach the target.

Prototype one structural change at a time. First prove that it reduces the intended counts, bytes and critical-path work; then run balanced complete-command pairs on real edits. Compare fresh discovery, post-restart discovery, ordinary edits and test edits separately. Verify exact rows, additions/removals, module-boundary changes, fields as dimensions, selections and test execution. Keep only changes whose measured gain justifies their complexity and risk.

## Earlier evidence

An earlier prototype reached 9.30 seconds after ordinary-source edits, with test-file edits mixed at about 20 seconds. The subsequent package-snapshot prototype was rejected after 18.60 → 55.76 seconds. See [the complete comparison and profile](NATIVE_GO_PACKAGE_TEST_SNAPSHOTS.md).

The first identity experiment now works for real test-file edits: [scoped getter content identity and native directory views](NATIVE_COLLECTION_GETTER_CONTENT.md) turn 800 discovery executions into one execution and 799 hits. Complete listing improves **18.10 → 16.24 seconds** across four pairs; root discovery still takes about 8.5 seconds and getter preparation about 7.5 seconds in wcprof. Ordinary-source edits show no additional gain. The prototype remains default-off on a separate engine, with the retained Rust-cache engine untouched.

The next order-of-magnitude experiment must reduce the 800 getter evaluations themselves while preserving ordinary collection behavior. Separately, inspect root discovery's repeated config checks against immutable module dependencies. The earlier live-config sharing approach was rejected for staleness; freshness is a required invariant.

A module-only follow-up now batches validation and owned-file discovery. Final confirmation improves test-file-edited listing **17.35 → 15.92 seconds** and ordinary-source-edited listing **10.39 → 7.56 seconds**. It removes 160 module evaluations and 1,510 SDK requests while retaining 799 unchanged discoveries. [Source, complete cohorts and scope review](NATIVE_GO_BATCH_PACKAGE_DISCOVERY.md).

The context-chain lead has now been tested. A depth benchmark improves by roughly 200× at depth 512, but complete listing does not improve: **13.59 → 14.51 seconds** after test-file edits and **6.70 → 6.77 seconds** after ordinary-source edits. Race tests and real collection checks pass. The candidate stays disabled; the profile still shows substantial context lookup cost. Existing sorting and ID shortcuts remain unselected.

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
