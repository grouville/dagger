# perf(filesync): skip directories outside the host glob prefix

While profiling Go test collection listing on dagger/dagger, I found that looking for test files in one package still walked the entire checkout. For example, `Workspace.glob("core/*_test.go")` visits unrelated directories even though every match must be under `core`.

Use the part of the pattern before the first wildcard to skip unrelated directories. The walk still starts at the workspace root and uses the existing matcher, so matching rules and result order stay the same.

The cost is a few extra prefix comparisons while walking directories. Patterns such as `**/*.go` have no fixed directory prefix and cannot benefit; the benchmark includes that case to check the overhead.

### Results

Comparing main `80699ac67a` with only this change, on a fixture with 24 modules, 24 packages per module and eight files per package:

| Pattern | Main | This PR | Memory allocated, before → after |
| --- | ---: | ---: | ---: |
| `module00/pkg00/*_test.go` | 9.28 ms | 0.10 ms | 1.24 MB → 22.60 kB |
| `module00/**/*.go` | 10.01 ms | 0.60 ms | 1.24 MB → 75.86 kB |
| `**/*.go`, whole-tree control | 14.13 ms | 14.12 ms | 1.47 → 1.47 MB |

Medians from four pairs of runs, alternating which version runs first. Both patterns with a directory prefix improved in all four pairs; the whole-tree case was effectively unchanged. Each sample ran for 100 ms with a warm filesystem cache. Fixture creation is excluded. Go 1.26.6, Linux amd64, `GOMAXPROCS=8`.

These measure file discovery separately. The effect on the complete Go test listing command has not yet been measured for this change alone.

### Reproducing

The tests compare matches and their order with the original full walk, including wildcard directories, exclusions, Unicode names, escaped characters and symlinks. They also check cancellation when the prefix does not exist:

```sh
go test -race -count=1 ./engine/client
```

To run the three benchmark cases:

```sh
GOMAXPROCS=8 go test ./engine/client -run '^$' -bench '^BenchmarkGlobHostPathLiteralDirectoryPrefix$' -benchmem -benchtime=100ms
```

[Raw measurements and instructions for comparing against main](https://github.com/grouville/dagger/tree/experiment/rust-native-cache/hack/rust-cache/experiments/standalone-go-collections/host-glob).
