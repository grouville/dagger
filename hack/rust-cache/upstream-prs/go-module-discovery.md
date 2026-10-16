# perf: reduce Go module discovery work

Discovering Go modules collects and sorts every owned file just to decide whether a module has any Go code. File filtering compares each filename with every nested module root. Package discovery also reads every matching test declaration when it only needs filenames. On `dagger/dagger`, this does substantial work before any test starts.

Stop validation at the first owned file, look up each file's parent directories in a temporary set of nested module roots, and append already ordered entries without traversing the sorted prefix twice. Request only filenames when discovering test packages. The existing insertion fallback preserves byte order, and both discovery paths share the same file-ownership predicate. The index is rebuilt within each call.

This branch builds on [package-scoped test-name discovery](https://github.com/grouville/go/tree/perf/package-test-discovery). The measurements below compare that branch with this follow-up.

| Case | Before | After | Allocated bytes | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Discover 80 module roots on clean dagger/dagger | 38.32 s | 12.85 s | 23.17 → 1.81 GB | 2/2 |
| List 2,495 owned Go files | 23.36 s | 3.57 s | 21.25 → 1.56 GB | 2/2 |
| Edited collection: 64 packages, 512 tests | 8.53 s | 7.65 s | 4.49 → 3.92 GB | 4/4 |

Balanced pairs with a fresh source edit and CLI process on every arm, warm engine/compiler caches, telemetry enabled and ordinary GC. Discovery outputs match byte for byte. The index-building cost is included. These are cumulative allocations, not peak memory. Earlier selected engine optimizations are enabled on both sides; full source and binary identities are recorded.

Smaller controls show mixed latency: 16 packages measure 2.39 → 2.44 seconds, and one package with 16 test files measures 1.33 → 1.41 seconds, both faster in 2/4 pairs. They allocate less. The full expanded test listing on dagger/dagger still reaches a 90-second diagnostic limit; no engine crash or OOM was reproduced.

The four focused checks pass. They cover file order, ignored files, nested ownership, working-directory lookup, Unicode names, selecting a failing test, and adding/replacing host-overlay tests. Separate wcprof captures have no dropped or unfinished operations: file-path reads fall from 512 to 64, while workload starts remain 65 and engine queries remain 1,194.

[Benchmarks, source snapshots and raw evidence](https://github.com/grouville/dagger/blob/experiment/rust-native-cache/hack/rust-cache/NATIVE_GO_DISCOVERY.md).
