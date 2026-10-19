# perf: look up source context only when evaluation fails

While profiling Go test collection listing, I found repeated work preparing error information during successful Dang evaluation. Each evaluation step looks up the source context used to report errors and wraps the Go context before evaluating the node, even when no error occurs.

Delay that lookup until an error needs source information. Successful evaluation can return its value directly. The explicit `EvalNodeWithContext` API keeps its existing behavior, including when the caller passes nil.

The tradeoff is an extra branch when handling an error. The benchmarks include failures so the saving on successful evaluation is not the only case measured.

### Results

Comparing main `da1bed304c` with only this change:

| Evaluation | Main | This PR | Allocated bytes |
| --- | ---: | ---: | ---: |
| Success, source context present | 189.75 ns | 14.85 ns | 48 → 0 |
| Success, source context under 128 context values | 670.65 ns | 16.17 ns | 48 → 0 |
| Failure, source context under 128 values | 1.34 µs | 1.37 µs | 136 → 88 |
| Failure, 128 values with no source context | 1.07 µs | 1.10 µs | 32 → 32 |

Medians from four alternating pairs. Both successful cases improved in every pair. The two failure controls had mixed timings, with this PR faster in two of four pairs. Success samples run for 100 ms, failures for 300 ms; context construction is excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

These isolate evaluation overhead. The complete Go collection listing gain has not yet been measured for this change alone.

### Reproducing

The tests check source filenames and locations on errors, explicit and nil contexts, cancellation, control-flow exceptions and invalid nil results:

```sh
go test -race -count=1 ./pkg/dang
```

To run the successful-evaluation cases:

```sh
GOMAXPROCS=8 go test ./pkg/dang -run '^$' -bench '^BenchmarkSuccessfulNodeErrorContext$' -benchmem -benchtime=100ms
```

[Raw measurements and instructions for reproducing successful and failed evaluation](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/lazy-error-context).
