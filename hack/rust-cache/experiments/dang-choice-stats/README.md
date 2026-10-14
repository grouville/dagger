# Optional parser choice statistics

The Rust module's engine CPU profile shows repeated string formatting and map
updates in Dang's generated parser, collecting ordered-choice statistics that
the engine never reads. This experiment makes those counters opt-in through the
existing `Statistics` option. Expression limits, debug support and telemetry
remain available. It does not retain syntax trees or invocation state.

The source change belongs in Pigeon, the parser generator. `pigeon.patch`
changes its template and generated template; `dang.patch` is the corresponding
generated change for Dang v2.1.4. `regression.patch` adds a Dang regression and a
benchmark using a real Rust module source supplied through `DANG_PERF_SOURCE`.
These are experimental patches, not a Dagger dependency update.

In separate local checkouts, apply `pigeon.patch` to Pigeon commit aa1e61c16975,
and `dang.patch` plus `regression.patch` to Dang v2.1.4. The benchmark compares
requested counters with the new default in the same binary:

```sh
CGO_ENABLED=0 go test ./pkg/dang -count=1
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang CGO_ENABLED=0 \
  go test ./pkg/dang -run '^$' -bench '^BenchmarkRustModuleParser$' \
  -benchmem -count=5 -benchtime=300ms
```

The existing Dang package tests and the focused regression pass. The regression
checks parsed syntax, error messages, expression limits, requested counters and
restoration of the original parser options. Five benchmark samples give median
parser times of 110.35 ms with counters and 67.41 ms without them. Allocations
fall from about 425,775 to 284,873 per parse; bytes fall from 20.42 MB to 18.34 MB.
This is a parser measurement, not a complete-command speedup.

The engine experiment uses the same source as
`experiment/rust-cache-dang-parsing`, with an isolated Go module file pointing at
the patched local Dang checkout. Compiler caches and telemetry settings match
the control. A separate five-pair series of fresh edits reduces the full
`dagger check rust:check` median from 695 to 637 ms; native Cargo medians are
181/183 ms. All ten checks pass, and invalid source fails on both engines. See
[the measurements](../../WCPROF_OCT13.md) for ranges and limitations.

Regenerating the Pigeon template and then Dang's parser produces the
engine-tested parser byte for byte. The focused regression fails on the original
parser and passes with the patch. Upstream adoption requires changing the
generator and then updating Dang; no upstream PR has been opened.
