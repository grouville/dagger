Generated Go entrypoints fetch the current function's metadata in 4 + 2A requests, where A is the number of supplied arguments. Read the parent, function name and argument values in one query before invoking the method. JSON stays serialized, and the existing argument decoder and return handling stay in place.

This changes the Go code generator. Entry points benefit after regeneration. It adds no engine API, locks, retained state or dependencies.

### Performance

The Rust compiler helper supplies 12 arguments: metadata requests fall from **28 to one**. A complete edited 64-package collection records **5,097 → 3,369 engine queries**, **768 → 0 argument-ID reads**, and the same **193 workload starts**.

| Complete edited Rust command | Before median | Branch median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| Collection, 1 package | 0.813 s | 0.689 s | 141 ms | 3/4 |
| Collection, 16 packages | 2.316 s | 2.225 s | 91 ms | 3/4 |
| Collection, 64 packages | 8.602 s | 8.253 s | 190 ms | 3/4 |
| Collection, 64 packages, confirmation | 8.922 s | 8.095 s | 884 ms | 7/8 |
| Workspace API, 64 packages | 0.917 s | 0.927 s | 4 ms | 3/6 |

The collection confirmation allocates **6.96 → 6.73 GB** and uses **46.85 → 42.77 engine CPU-seconds** per command. Allocations are cumulative, not peak memory. The gain varies across cohorts. The workspace control establishes no speedup and allocates about 7 MB more.

Each arm makes a fresh source edit and starts a fresh CLI. The engine and compiler caches are warm; telemetry and normal GC stay enabled. Orders balance before/after placement. Profiling runs separately. The experiment changes only the Rust helper's generated dispatch block, which matches this template byte for byte. It uses diagnostic engine `2a32d997c29c…`; it is not a benchmark of an engine built from today's main.

### Validation

The standalone change is based on main `ff0b029a4d`. A runtime regression compiles the actual generated dispatcher and uses the real SDK HTTP transport. It checks empty arguments, exact JSON values, method errors, metadata errors and one metadata request. The mock serves the old request shapes too: main preserves the data but fails the request-count assertion; the patch passes.

```sh
go test -count=1 -run '^TestDispatchInputs$' ./cmd/codegen/generator/go/templates
go test -race -count=1 ./cmd/codegen/generator/go/templates
go test -count=1 ./cmd/codegen/generator/go
```

Rust integration checks cover arbitrary subsets, selected/excluded test failures, excluding an invalid crate, repair and the workspace API. Worker inputs and native-cache format are unchanged. Server-side decoding still scales with argument count, and fine collections remain much slower than the workspace batch.

[Complete evidence](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/go-module-batched-inputs) retains both cohorts, the flat control, all samples, source hashes, final profiles and the failing-main regression. An earlier CPU capture overlapped a unit test and is marked accordingly; only the final isolated captures support CPU attribution. No PR is open.
