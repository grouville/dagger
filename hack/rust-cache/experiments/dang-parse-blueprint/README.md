# Cached parsing with fresh syntax per call

Apply `dang.patch` to Dang v2.1.4 after the
[opt-in parser-statistics patch](../dang-choice-stats/README.md):

```sh
git apply --unidiff-zero /path/to/dang.patch
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -race -count=1 ./pkg/dang ./pkg/hm
go test -count=1 \
  -run '^TestDang/(TestLanguage|TestFormatLanguage|TestErrorMessages)$' ./tests
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -run '^$' -bench '^BenchmarkRustModuleBlueprint$' \
  -benchmem -benchtime=1s -count=3 ./pkg/dang
```

The cache stores construction instructions from the uninferred syntax and
creates fresh pointers and slices for each directory evaluation. Its key includes
the filename and current file contents. Inference still uses the current
imports, schema and client. Unsupported syntax falls back to the original parse.

Focused tests cover syntax mutation, source invalidation and errors, concurrent
evaluation, current-client and current-schema behavior, and the language corpus.
The benchmark accepts the actual Rust module through `DANG_PERF_SOURCE`.

This is a prototype, not a dependency update. Its 128-entry cache needs a byte
budget and eviction coverage before adoption. The first full-command comparison
is noisy and does not establish a general speedup; see the
[measurement report](../../NATIVE_PARSE_CACHE.md).
