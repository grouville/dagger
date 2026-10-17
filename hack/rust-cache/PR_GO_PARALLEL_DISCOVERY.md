Go test listing waits for each module's validity checks and package discovery in turn. These independent reads form two serial chains before the test collections can expand.

Use Dang's ordered parallel selections for both steps, then apply the existing filtering and concatenation. The change is seven added lines and five removed lines across two functions. It preserves collection keys, ordering, source policy and test granularity.

Full listing on dagger/dagger, after both module versions have completed their first full listing:

| Order | Before | After |
| --- | ---: | ---: |
| Before, after | 88.39 s | 66.42 s |
| After, before | 88.90 s | 67.80 s |

Median time decreases **88.65 → 67.11 seconds**. All four commands return identical 4,398 rows, exit successfully and have the same invocation count. Each starts a new CLI and edits a source comment on a warm engine. Telemetry and normal GC remain enabled. No test or compiler runs during listing.

The tradeoff is more overlap: total engine CPU rises 299.21 → 309.40 seconds and allocations rise 43.84 → 44.28 GB. Sampled peak heap is 12.33 → 12.21 GB; these pairs do not establish a memory improvement. The engine includes other performance experiments held constant across both arms, so these are isolated module-change measurements on that engine, not stock upstream timings.

The existing collection, subdirectory, module-discovery, invalid-root and test-collection checks pass, including exclusions, nested modules, overlays, Unicode and ordering. Both files pass the Dang v2 formatter. No new test duplicates those cases.

Measured with `dagger check --module go --check test --list --all` on dagger/dagger `ff0b029a`, comparing Go module `b5dd9434` with the two commits in this branch. Earlier discovery-only and initial-cache-population attempts are retained with the benchmark evidence. Full listing remains slow; this removes two serial discovery chains.
