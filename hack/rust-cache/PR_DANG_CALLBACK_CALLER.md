# perf: avoid building an empty object for every callback

While profiling Go test collection listing, I found repeated allocations when Dang calls functions passed to operations such as `map` and `each`. Every callback builds an empty type and object to represent its caller.

A concrete Dang function only reads that caller's `self`; its arguments and local variables live in a separate scope created from its closure. Reuse one empty caller for those functions. Other implementations of `Callable` can modify their caller, so they still receive a fresh object.

The cost is one shared empty object kept for the interpreter's lifetime, plus a type check per callback. The custom-callable control measures the path that cannot benefit.

### Results

Comparing main `da1bed304c` with only this change:

| Callback | Main | This PR | Allocated bytes | Allocations |
| --- | ---: | ---: | ---: | ---: |
| Dang function | 6.85 µs | 4.99 µs | 2,648 → 1,464 | 30 → 17 |
| Custom callable, control | 1.87 µs | 1.72 µs | 2,048 → 2,048 | 19 → 19 |

Medians from four alternating pairs. Dang function calls improved in every pair; the custom control was faster in three of four, with unchanged allocation counts. Function samples run for 100 ms and controls for 300 ms; program loading is excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

These measure callbacks, not the complete Go collection listing command.

### Reproducing

The tests check concurrent calls with different arguments, captured `self`, and custom callables that modify their caller:

```sh
go test -race -count=1 ./pkg/dang
```

To run the function callback benchmark:

```sh
GOMAXPROCS=8 go test ./pkg/dang -run '^$' -bench '^BenchmarkCallbackCaller$' -benchmem -benchtime=100ms
```

[Raw measurements and instructions for reproducing the function and custom-callable cases](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/callback-caller).
