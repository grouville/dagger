# Cost when there is little to share

Both arms use the same fixture. Each persisted output group contains exactly one result; the fixture verifies the imported result count, group sizes and lookup indexes. The second benchmark adds fresh results through GetOrInitCall.

The four-pair initial cohort uses one operation per sample. The six-pair longer cohort reuses those binaries with one second per case. Both cohorts and all slower samples are retained. Build and fixture setup/closing are excluded. Production files are identical to the original measured candidate; the later source commit replaces helper-only benchmarks with these controls and improves the commit message.

The PR includes these benchmark controls. From its checkout run:

```sh
GOMAXPROCS=8 go test ./dagql -run '^$' -bench '^BenchmarkResultList(SingletonImport|FreshInsert)$' -benchmem -benchtime=1s
```

For a main comparison, add the same fixture to both original overlays and compile before/candidate test binaries as described in the parent README. The initial JSON overlays and build logs retain the exact original commands and file mappings.
