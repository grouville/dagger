# Standalone restored-cache import and pruning

The control is Dagger main `80699ac67a1c72dc38d30c4186105cd9dd3afde6`. The candidate adds only the production changes in the linked source branch. Both binaries contain identical import/prune fixtures, using APIs that exist on main. The full source branch separately passes `go test -race ./dagql`.

Four alternating before/candidate and candidate/before pairs use Go 1.26.6, GOMAXPROCS=8 and `-benchtime=1x`. Fixtures verify imported result counts, no persistence reset, and successful pruning. Setup, close and compiler time are outside the measured operation. All observations, including the first slower baseline, are retained. This does not measure complete Go listing or cold filesystem performance.

`source.json` pins both commits. `layout.json` maps the saved source files into a fresh main checkout. `before.json` and `candidate.json` retain the exact original overlay mappings; replace their checkout and evidence directory prefixes when replaying. The two fixture files belong in both arms; the four production files belong only in the candidate overlay. Neither arm contains other engine experiments.

Build each arm once with its overlay and run the resulting binaries in alternating order:

```sh
GOMAXPROCS=8 go test -p=2 -c -overlay=/path/to/before.json -o /tmp/cache-before ./dagql
GOMAXPROCS=8 go test -p=2 -c -overlay=/path/to/candidate.json -o /tmp/cache-candidate ./dagql
GOMAXPROCS=8 /tmp/cache-before -test.run='^$' -test.bench='Benchmark(CacheImportWideOutputClass|MetadataPruneRestoredWideOutput)/(64|1024|4096)$' -test.benchmem -test.benchtime=1x
GOMAXPROCS=8 /tmp/cache-candidate -test.run='^$' -test.bench='Benchmark(CacheImportWideOutputClass|MetadataPruneRestoredWideOutput)/(64|1024|4096)$' -test.benchmem -test.benchtime=1x
```

Use the same working directory on both sides. The large baseline prune takes tens of seconds. Timed process duration also includes fixture setup and is not the ns/op result. The earlier rejected harness referenced a candidate-only helper; it produced no samples and is retained in `../restored-index-harness-attempt-01/`.
