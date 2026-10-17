Listing tests resolves every package's containing module again, even though package discovery already found it. On dagger/dagger this executes 800 nested SDK calls to `Gomod.module`.

Keep the discovered module roots with the package collection and pass the matching root to each package. Before using it, compare a cached digest of the workspace's `go.mod` snapshot. If the caller supplies a workspace with different module boundaries, use the existing lookup. The fields are optional so packages without discovery metadata retain their existing behavior.

Two alternating pairs on dagger/dagger, after both module versions have completed their first full listing:

| Order | Before | After |
| --- | ---: | ---: |
| After, before | 68.75 s | 57.85 s |
| Before, after | 68.00 s | 55.77 s |

Median complete-command time decreases **68.37 → 56.81 s**. Engine CPU falls **290.39 → 237.43 CPU-seconds**, allocations **44.25 → 35.65 GB**, and SDK invocations **1,762 → 963**. Every command returns identical 4,398 rows and exits successfully. A fresh CLI and source edit are used each time; telemetry and ordinary GC stay enabled. No compiler or test runs during listing.

The first source-population pair is retained separately: 66.83 s before and 68.13 s after. The candidate performs more uncached getter work on that first listing; this comparison establishes an improvement for subsequent edited-workspace listings, not a first-load speedup.

wcprof confirms that the 800 module lookups disappear. The fingerprint executes once and is read from cache for the other 800 callers. Test discovery falls from about 30 to 18 seconds in diagnostic captures; package discovery remains about 20 seconds. Full listing is still slow.

Existing ownership, collection, subdirectory, test, binary and generation checks pass. The new integration check retains a package, adds a nested `go.mod`, and executes its test in the edited workspace. It fails without the fingerprint guard and passes with it. Adding and removing a real test declaration on dagger/dagger also produces exactly 4,399 then 4,398 rows.

This stacks on the parallel-discovery changes. The engine includes existing experiments held constant across both arms; these are module-change measurements, not stock-engine timings. This patch changes the Go module and its shared `gomod` library in the same repository. It changes no engine lock or cache policy.

[Review branch](https://github.com/grouville/go/tree/experiment/package-module-ownership). No PR is open.
