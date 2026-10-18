Review draft for `grouville/go:experiment/batch-package-discovery`. Extract the discovery commits onto the upstream Go module before opening a PR; this branch includes the earlier native-snapshot experiment. No PR is open.

Title: **Batch Go package discovery**

Listing checks in a workspace with many Go modules validates the modules, then makes additional library calls to list each module's files. Those calls repeat client, schema and configuration preparation.

Return validated module facts and owned files in one library call. Build the module-boundary index once per discovery, and use the same files for package classification. Keep the existing public ownership helpers and collection selection behavior.

On dagger/dagger, with 80 modules and 4,398 listed test checks:

| Complete listing after an edit | Before | After |
| --- | ---: | ---: |
| Test-file edit | 17.35 s | 15.92 s |
| Ordinary Go source edit | 10.39 s | 7.56 s |

Four balanced pairs per workload, warm engine and fresh CLI, telemetry and GC enabled, through successful exit and cleanup. Every command returns identical rows. Test edits improve in all four pairs; source edits improve in three. The slower first candidate removal is included. These measurements use the existing development engine and native-snapshot module prototype; they are not stock-main timings.

Allocation medians fall 18.68 → 17.39 GB for test edits and 7.91 → 6.33 GB for source edits. A separate wcprof capture records 964 → 804 module evaluations and 3,803 → 2,293 SDK requests while preserving 799 discovery hits and one changed package.

The new index uses balanced immutable-map merges and checks path ancestors. It is local to the invocation, so host module roots and files stay fresh. No locks or cross-call cache are added. Existing sort costs remain.

Seven focused checks pass, including real test binaries and comparisons against existing ownership rules. Coverage includes invalid and empty modules, nested boundaries, ignored files, sibling prefixes, Unicode ordering, overlays and changed working directories. The global-index rule is confined to the batch path to preserve existing public helper behavior. The remaining full Go-module suite and standalone upstream validation are still required before marking a PR ready.
