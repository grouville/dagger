# Package-search verification with one shared workspace

[Go draft #68](https://github.com/dagger/go/pull/68) now contains the package-scoped replacement, commit `bc0d99eb747f78d38c8e93d86a36dee730b9115a`, directly on Go main `334136faaa`. The file-by-file version with the filename regression is no longer the PR source. The new implementation still depends on [engine #14740](https://github.com/dagger/dagger/pull/14740) for host-workspace package directories created through Dagger.

## Complete-command comparison

Both versions are installed under separate aliases in the same fixture workspace. Its configuration remains fixed; each command selects one alias. This removes the separate-host-root difference in the [preceding cohort](../scoped-search-followup-oct19/). Each measured pair changes a test name. Each command edits source and test comments, starts a new CLI and validates the expected names, complete row order and successful cleanup. Warmups add a test and then remove it. All commands use unchanged engine `80699ac67a`, normal telemetry, ordinary cache policies and no profiling.

Each row below has six alternating pairs, after two warmup pairs:

| Fixture | Main median | Change median | Faster pairs | Allocated bytes, main → change |
| --- | ---: | ---: | ---: | ---: |
| Identical-code control, 16 packages | 8.248 s | 8.252 s | 3/6 | 6.48 → 6.40 GB |
| 16 packages, 128 tests | 7.94 s | 6.16 s | 5/6 | 6.42 → 4.59 GB |
| 1 package, 128 tests in 16 files | 3.85 s | 3.68 s | 4/6 | 1.77 → 1.72 GB |
| 1 package, 8 tests in 1 file | 2.29 s | 2.27 s | 4/6 | 0.911 → 0.910 GB |

The many-package case uses 42.04 → 31.98 engine CPU-seconds. Allocated bytes are cumulative engine allocation, not peak resident memory. The single-package controls establish little benefit; they do not show the extra per-file search cost of the old implementation. The preceding cohort was more variable and included a slower single-package control. Keep both cohorts visible. Column medians and median paired savings are different statistics; both are retained in the JSON rather than substituted for one another.

The submitted production file has SHA-256 `fda6da4ddedd2d5a903c578e3abd57c93ba4e7f87ede30cca981304f866c5fc9`, unchanged from the preceding timing and wcprof captures. Those captures execute 18 workspace searches in both versions and read 2,176 → 256 matching test lines, with no dropped events or unfinished operations. The final commit additionally cleans up fixture names and checks mounted content. Both main and the candidate pass the mounted/literal-filename check; the final host-workspace added-file/new-package check passes on the standalone fixed engine. Existing collection execution coverage was already run against this production source. The exact submitted patch is included here.

## Full dagger/dagger remains unresolved

The first full-repository run with this standalone Go change hits the 240-second cutoff with **zero rows**. It is unprofiled, includes the fresh CLI and normal telemetry, and is a failed attempt rather than a timing win. The earlier main attempt also timed out. At cancellation the trace is still inside `Go.packages`, with a `GomodGoMod.subpath` call active. Narrowing package test searches does not resolve that preceding module-discovery bottleneck.

An independent inventory of the current root-module source finds 4,482 test keys before adding the measurement's test, or 4,483 with it. This uses tracked files, the existing root-module exclusion rules and the existing matcher through ripgrep. It is an expected inventory, not a successful collection output. The checkout is `c5456d9cbf`; the older 4,398-row experiments used a different source state. Source files and the installed-module configuration are restored after the attempt.

The next experiment batches the existing module test-selection rules. Its first list-membership implementation is not selected: repeated membership checks can become quadratic. The corrected experiment returns one boolean per input path and uses its index. It remains separate from Go #68 and is not a new PR or a measured gain yet. Existing engines and volumes are retained.
