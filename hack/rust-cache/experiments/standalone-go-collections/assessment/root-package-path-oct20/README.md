# Root-module package-path identity: hold

The isolated candidate is based on Go main `8a1d6ad09c909a541e7e5fa319bddb5dba83d20b`, on the stock Dagger main `23b004afe665eb4cc8a44767ba532fcb5cda2020` engine and CLI. It does not include the sorting patch. The shared library explicitly returns a relative path unchanged for the root module; the candidate handles that identity in `GoModule.packagePath` and retains the existing library call for other modules.

The full collection command uses one root Go module, 16 packages and 16 tests. The source comment and one test name change on every invocation. Module installation path and configuration remain fixed. Both excluded warmups and all four measured commands return the exact expected rows in order and finish cleanup. Commands are sequential, with telemetry and normal GC; profiling is disabled during measurements.

| Pair | Main | Candidate |
| --- | ---: | ---: |
| 0 | 6.645 s | 6.852 s |
| 1 | 14.833 s | 6.079 s |

The candidate is faster in only one of two pairs. The median difference is dominated by the second baseline run, so it does not establish a reliable latency benefit. Host CPU pressure during measured commands is substantial; raw counters are retained. No performance percentage or full-repository improvement is claimed.

Separate wcprof commands confirm the mechanism: 16 `GomodGoMod.subpath` executions and 16 hits in the baseline become none in the candidate. Both still execute one `Go.packages` and 16 `GoPackage.tests` calls. Those diagnostic runs have no dropped events or unfinished operations and return the correct rows through successful cleanup. They are excluded from timings.

This experiment does not meet the publication quality bar yet. There is no fork branch or PR for it. Small and nested-module controls and a stable independent end-to-end benefit would be required before publishing. The more general target remains repeated Dang preparation across executed function calls.
