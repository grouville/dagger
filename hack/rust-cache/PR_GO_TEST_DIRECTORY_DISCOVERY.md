Review draft for `grouville/go:experiment/snapshot-test-directories`. Port onto the upstream module before opening a PR: its parent includes the experimental snapshot API. No PR is open.

Title: **Discover Go test directories once per snapshot**

Listing the test collection asks whether each package directory exists in an already prepared native test-source snapshot. On dagger/dagger, that adds 800 SDK requests after a test-file edit.

List the snapshot's test files once and carry their directories into the package collection. Each getter selects its usual directory view when the package has direct test files. Preserve the fallback when directory information is absent, source overrides and per-package discovery caching.

| Complete listing after an edit | Before | After |
| --- | ---: | ---: |
| Test-file edit | 12.22 s | 11.25 s |
| Ordinary Go source edit | 6.01 s | 5.98 s |

Four balanced pairs per workload, warm engine and fresh CLI, through successful cleanup with telemetry and ordinary GC. Test edits improve in every pair; source results are mixed. Test-edit CPU falls 68.92 → 59.24 CPU-seconds and cumulative allocation 16.56 → 15.43 GB. Cold effects are unmeasured.

Separate wcprof captures confirm 800 existence queries become one directory listing and SDK requests fall 2,293 → 1,494. Evaluations remain 804. The new list adds receiver payload and uses linear membership, so this does not solve collection scaling. The single profiled candidate runs slower; latency gains come from the unprofiled pairs.

Seven focused commands pass, covering direct and descendant tests, absent directories, empty files, nested modules, literal and Unicode paths, source overrides, additions, removals, working directories and execution. All 24 complete timing commands return correct rows and exit successfully. Broader upstream compatibility checks remain before marking this ready.
