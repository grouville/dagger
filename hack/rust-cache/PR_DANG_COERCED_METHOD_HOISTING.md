# perf(dang): recognize typed methods during declaration classification

Type checking wraps typed methods in a conversion node. The declaration classifier only recognizes a directly held function, so it treats those methods as variables needing initialization. Reconstructing an object then allocates and runs a deferred initializer just to create each method.

Look through the conversion node when choosing the declaration phase. Evaluation still uses the original node, retaining its conversion, receiver and defaults. This was found while reducing Go test collection listing overhead on dagger/dagger.

### Performance

Complete-command measurements use `dagger check --module go --check test --list --all`.

| Workload | Before | After |
| --- | ---: | ---: |
| Complete listing after a test-file edit | 14.31 s | 12.71 s |
| Engine CPU | 78.97 CPU-s | 68.79 CPU-s |
| Cumulative engine allocation | 17.40 GB | 16.62 GB |
| Receiver preparation: 800 packages, 80 owners, 32 methods | 2.50 s | 1.68 s |

Complete test-edited listing improves **11.2%**, in all four alternating pairs. Expansion reconstructs 64,800 nested objects in this workload.

Ordinary-source listing is **6.75 → 6.90 s**, faster in only one of four pairs; no gain is established there. Every command starts a fresh CLI on the same warm experimental engine, includes telemetry and successful cleanup, and returns correct rows. These are not stock-release or cold-start measurements.

### Validation and tradeoffs

The regression fails on pristine Dang da1bed304c and passes with the patch. It checks a parsed, inferred typed method, its initializer classification, current receiver and default argument. Another case covers an initializer calling a later method.

The full upstream interpreter race suite and seven focused Go/library checks pass. All 20 complete listings succeed. The standalone production change touches only `pkg/dang/block.go`, adding no cache, lock or API.

[Standalone patch and validation](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/experiments/dang-coerced-method-hoisting/method-hoisting.patch). [Complete measurements](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_DANG_COERCED_METHOD_HOISTING.md).
