# Direct cache-object input: rejected after retention testing

The experiment removes an explicit metadata round-trip from Dang to the Go compiler helper, but retains previous cache objects through the function input graph. The selected module stays on the separate-field path. Its modest timing benefit does not justify growing dependency ancestry.

Tested code: [4f427f2f](https://github.com/grouville/dagger-rust/commit/4f427f2f2777f8d28e0d1e48b7071e0a4d43abe9), based on `cd6d25e`. The fork branch `experiment/native-cache-object-input` also records the rejection. No PR is open.

## Change and correctness

The Go helper accepts an optional `previousCache *Cache`, retaining the existing manifest/token/snapshot arguments as an alternative. A supplied plan takes precedence; otherwise it uses the previous plan. Dang passes the native cache object instead of selecting its fields and rebuilding their arguments. The hand-written change adds 18 lines and removes 18, plus the generated invocation/client update. Stored history, worker source and compiler-result keys stay unchanged.

The large history contains a 272,568-byte manifest; the 130-action history contains 125,496 bytes. Object passing removes the explicit field read and large argument construction in Dang. The Go runtime still receives serialized object state, so this is not a claim that metadata transport disappears.

The main package compiles and the model, replay and worker race suites pass. All six existing histories retain every compiled result: 130/130, 1,026/1,026 and 6/6. A separate 130-action check verifies an empty project cache (0 hits), same-source reuse (130), a used-source edit (128), invalid Rust rejection, repair (130) and reversion (130). Manually restored old cache fields still reuse 130/130.

The first negative-check harness expected the Rust diagnostic in the top GraphQL message. The engine returns an exit-code envelope and emits the Rust diagnostic through logs. The corrected check verifies both and completes repair/reversion. The first local build also required regenerating the checked-in invocation wrapper for the new parameter. Neither is presented as a product defect.

## Complete edited commands

Both arms use shell discovery with the local script, the same warm buffered engine, source snapshot seeds, compact scalar restoration and enabled telemetry. Each command has a fresh client and a fresh used-source edit. Each cohort contains eight pairs with rotating order; the second exchanges physical histories. Priming precedes timing, wcprof is off, and all admitted observations remain included. The baseline is `cd6d25e`; engine SHA-256 is `a75afeec2c7fa014af451b8ba2eb87f1273990a83b2a5e45944031dd9da4aeaa`.

| Cohort | Command | Fields median | Object median | Cargo median | Median paired saving | Faster pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| paired | 130-crate direct check | 0.693 s | 0.663 s | 0.128 s | 37 ms | 6/8 |
| paired | 1,026-crate grouped check | 1.887 s | 1.772 s | 0.808 s | 67 ms | 7/8 |
| paired | small workspace tests | 1.034 s | 1.055 s | 0.521 s | -20 ms | 2/8 |
| crossover | 130-crate direct check | 0.664 s | 0.643 s | 0.128 s | 30 ms | 5/8 |
| crossover | 1,026-crate grouped check | 1.705 s | 1.753 s | 0.798 s | 22 ms | 4/8 |
| crossover | small workspace tests | 1.040 s | 1.042 s | 0.512 s | 16 ms | 4/8 |

The direct control shows roughly 30–37 ms paired savings. Large and small results do not establish a consistent benefit. One baseline small-workspace sample takes 22.151 seconds and remains included. Median differences and paired medians are reported separately.

## Ownership changes the decision

A separate owned engine runs the same four-action fixture for each implementation, with fresh command sessions and twenty unique app edits. Pruning occurs initially and after edits 5, 10 and 20. Each edit reuses 3/4 results; every post-prune check reuses 4/4. The main performance engine is not pruned.

| Edit checkpoint, after pruning | Fields: reachable results | Object: reachable results | Fields: snapshot references | Object: snapshot references |
| --- | ---: | ---: | ---: | ---: |
| initial-pruned | 307 | 316 | 51 | 51 |
| edit-5-pruned | 321 | 433 | 59 | 110 |
| edit-10-pruned | 321 | 548 | 59 | 167 |
| edit-20-pruned | 321 | 768 | 59 | 279 |

These are the latest cache object’s explicit dependency closures, not whole-engine result totals. At edit 20, the object variant retains 24 `RustCompilerCache` and 24 compilation objects in that closure, versus one of each with flat fields. Neither has mutual ownership cycles. The input object keeps earlier calls reachable; limiting entries in the stored manifest does not bound this ancestry. Snapshot references are graph references, not unique physical storage bytes.

The initial cleanup on the separate engine takes 230 seconds while deleting old snapshot file trees. A 10-second CPU capture samples 3.84 CPU seconds, with 91% in syscalls and most cumulative work under `os.RemoveAll`. This is maintenance evidence, not edited-build latency or a new lock bug. Subsequent retention checkpoints finish normally.

Keep the flat-field representation. A replacement must retain the native files and directories needed by the latest cache while bounding its dependency on older computations. Dropping a cache limit or ignoring the growing closure would not satisfy that requirement.

Evidence: [cache-object-input](experiments/cache-object-input/). The archived compact graphs retain IDs, types, dependency edges and snapshot references for independent recounting; full value payloads are excluded.
