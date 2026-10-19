# Current-main review

Three correctness fixes independently reproduce on current upstream main and pass with their fixes. Their draft PRs are Dagger #14736, Dagger #14737 and Dang #194. Both Dagger fixes use c5456d9cbf; the Dang fix uses bf649b8d. The Dagger focused regressions run with the race detector; the Dang fix also passes the full interpreter race suite. The three source branches contain no other proposal.

Four behavior checks pass for the new Go batching experiment: its batch selection check, the existing Gomod and Go selection checks, and binary building. It reuses the original selection method, preserves paths, ordering and duplicates, and avoids a call for an empty package list. It is pushed to the fork without a performance PR; its full-command gain remains unmeasured.

The typed-method and callback proposals independently pass the complete Dang race suite on bf649b8d. That verifies correctness, not the old performance claims. The error-context patch no longer applies after upstream runtime changes and is held for a fresh review. The failed apply is retained in checks.json; it is not a failing behavioral test.

The real-repository runs use the root Go module selection from the earlier listing experiment and keep discovery and generation enabled. The source is c5456d9cbf, Go module 334136faaa, engine/CLI 80699ac67a. The post-release commit changes generated clients and version constants, not the measured engine implementation. Other repository tool modules are not installed in this benchmark workspace.

Both attempts failed to produce the list: initialization was cancelled at 240 seconds, and the full diagnostic at 900 seconds. The first attempt includes one late CPU capture and is excluded from timing comparisons; the second has wcprof and engine/CLI CPU sampling throughout. Neither is a valid complete-command latency, speedup, or successful-cleanup result.

The completed discovery operation in the second capture took 623 seconds under profiling. It contains 705 Gomod.at calls, 706 selected calls and 726 subpath calls. The union of the first two classes covers about 260 seconds; subpath durations total about 173 seconds. These identify repeated module setup as a target, not a measured gain for the batch change. Summed concurrent durations in classes.txt must not be read as elapsed command time. The cancelled recording has no dropped events but still has open operations at its first dump.

The raw 15 MB compressed wcprof recording and all CPU windows are retained locally; the manifest records the dump hash. Drivers, baseline metadata, failed command output and useful test logs are included here. No existing engine or volume was reset, restarted or deleted. Normal telemetry and cache policies remain enabled.
