[Draft Go #68](https://github.com/dagger/go/pull/68) · [current source](https://github.com/grouville/go/tree/perf/review-package-test-discovery)

This is part of the work to make Go test collection listing faster. To find one package's test names, the Go module currently expands every matching test in the module and filters by filename. The source search is shared, but expanding and filtering its results is repeated for every package.

Search each package's own immutable test files instead. Keep the same rules for recognizing test names and the same order, including workspaces assembled from Dagger directories. The module-wide search used to find package paths stays in place.

Median complete `dagger check --module go --check test --list --all` commands, comparing this change alone with Go module main:

| Workspace | Main | This change | Engine allocations, main → change |
| --- | ---: | ---: | ---: |
| 16 packages, 128 tests | 18.91 s | 11.16 s | 7.06 → 3.89 GB |
| 1 package, 8 tests in one file | 4.21 s | 4.20 s | 0.859 → 0.858 GB |
| 1 package, 128 tests in 16 files | 7.02 s | 8.10 s | 1.79 → 1.94 GB |

Four alternating pairs per workspace. All four many-package pairs improve; engine CPU falls 51.58 → 29.81 CPU-seconds. Each command returns the expected ordered rows and exits successfully, including cleanup. The engine is warm, each CLI is new, and each command follows a fresh source and test-file comment edit. Telemetry is enabled through a local receiver; profiling is off during timing. Listing runs no Go tests or builds.

A separate wcprof capture counts 2,176 → 256 reads of matched test lines, with zero dropped events or unfinished operations. This confirms that the change removes repeated result expansion.

The cost is a search for each test file: the single-package, 16-file case starts 16 searches where one previously sufficed. The one-file control establishes no gain. The many-file control is faster in only two of four pairs and its median increases by 1.08 seconds, alongside the higher CPU and allocation cost. A separate comparison using identical module code on both sides measures 15.72 → 15.71 seconds over two pairs, with one pair faster on each side.

Both arms use the same upstream engine (`80699ac67a`), with no other Go module changes on top of main `334136faaa`. This is a generated-workspace measurement; it does not establish the time to list all of dagger/dagger's tests.

The existing collection check passes, including selected test execution, package isolation, failure reporting, build constraints, nested modules, ordering and directory-backed workspaces. The added Unicode test and parameter names cover the existing matching rules. Formatting passes.

[Fresh raw measurements, checks and profiles](../experiments/standalone-go-collections/assessment/independent-followup-oct19/). Earlier experimental-engine comparisons measured test execution at 4.52 → 2.36 s for 16 packages and 55.11 → 8.12 s for 64 packages. Those are different commands and engines; they are not the listing figures above. [Earlier evidence](../experiments/rust-go-test-collections/).
