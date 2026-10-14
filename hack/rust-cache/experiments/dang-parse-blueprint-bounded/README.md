# Bounded cached parsing

This extends the [fresh-syntax prototype](../dang-parse-blueprint/README.md) with
weighted eviction and regressions for eviction, oversized files, and concurrent
misses. Apply this directory's `dang.patch` to Dang v2.1.4 after the
[opt-in statistics patch](../dang-choice-stats/README.md). It contains the whole
prototype; do not also apply the earlier fresh-syntax patch.

```sh
git apply --unidiff-zero /path/to/dang.patch
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -race -count=1 ./pkg/dang ./pkg/hm
DANG_PERF_SOURCE=/path/to/dagger-rust/main.dang \
  go test -run '^$' -bench '^BenchmarkRustModuleBlueprint$' \
  -benchmem -benchtime=1s -count=3 ./pkg/dang
```

The cache permits 128 entries and 64 MiB of accounted construction weight.
Weight includes construction instructions, child slots and detached string
bytes. It estimates retained memory; it does not claim exact Go heap accounting.
Oversized or unsupported syntax skips caching and still parses normally.
Construction and parsing run outside the cache lock. Concurrent misses publish
one retained entry, and callers may finish using an entry after eviction.

The local memory probe after fifty versions of the Rust module retained fourteen
entries, 63,917,252 accounted bytes and a measured heap delta of 22,952,072 bytes.
That probe is an experiment artifact, not part of the proposed regression suite.

`phase-profile.patch` provides the same diagnostic callback as the earlier study,
with parsing, inference and evaluation now recorded as siblings. Apply it to
both benchmark libraries. The corresponding
[engine instrumentation](../../module-preparation-profile.patch) is unchanged.
These diagnostic hooks are not a proposed runtime API.
