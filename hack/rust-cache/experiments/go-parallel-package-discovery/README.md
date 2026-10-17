# Ordered parallel Go discovery

`go-parallel-package-discovery` compares serial package discovery with an ordered parallel selection. `go-parallel-module-validation` measures the additional validity-check selection against the first change. Initial full commands on new module source identities perform additional calls; all of those observations remain included.

`go-parallel-discovery-combined` is the direct confirmation against the original module after both source identities have completed full listings. All four arms have 1,764 session-flush requests, return the same 4,398 rows and exit successfully. Median time is 88.65 → 67.11 seconds; engine CPU is 299.21 → 309.40 seconds and allocated bytes are 43.84 → 44.28 GB. This is a warm experimental engine with fresh CLI/source edits, telemetry and ordinary GC; no cache reset or compiler/test execution occurs during listing.

`source` preserves the measured and final source. The packages-only source receives formatter/comment cleanup after its timing cohort; combined confirmation uses the final formatted sources. `profile-root-selection` contains the wcprof capture, CPU and allocation profiles and goroutine snapshots for the first change. Profiled time is diagnostic, not a benchmark. Its header reports zero dropped events and no open operations.

Two goroutine samples show 794 and 767 requests waiting in `getOrInitClient` on the session lifecycle mutex. The active initialization is in interface reconciliation in one sample and metadata cloning in the other. This identifies a next investigation, not a measured engine optimization. Existing interface snapshots are still disabled.

No PR is opened.
