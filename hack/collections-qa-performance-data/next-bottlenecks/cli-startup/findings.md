# Current CLI startup and traversal audit

Read-only audit of `shutdown-overlap/pairs/shared-512.cpu` and its runtime trace,
with `/tmp/collections-perf/rebase-main/dagger`. Capture duration 2.59 s,
520 ms sampled CPU. Values below are individual profile observations, not medians
or mutually exclusive pieces of the full command. Cloud drain is out of scope.

* `LoadDefaultLabels` / `WithGitLabels`: 10 ms sampled CPU, in Go-git's reference
  enumeration. The earlier 220 ms checkout figure does not describe this current
  greetings-api run. Profiling starts before the first load. Three source call
  sites are protected by the same process `sync.Once`, so this is not three Git
  metadata loads. `repo.References()` still scans all refs merely to identify
  matching local branch/tag labels: an O(refs) scalability concern, but not the
  major current profile cost. Replacing it needs to preserve detached-head/tag
  semantics and avoid introducing stale cross-invocation labels.
* `Client.Connect`: 39.11 ms of synchronization wait, primarily 36.46 ms in initial
  Buildkit `Wait`/Info. `docker version` availability additionally consumes
 16.14 ms syscall waiting, outside that sync profile. Avoid summing profile-wide
  background goroutine lifetimes: `startSession.func2`'s 2.38 s is the long-lived
  attachables server, not 2.38 s spent starting a session.
* `newBuildkitClient` calls `Wait`, which issues Info, then calls Info again.
  The second request waits 0.47 ms in this profile. Reusing the successful response
  could remove one RPC, preserving Unavailable retries/version checks, but it
  cannot plausibly account for the main gap to 500 ms.
* Filesync sender walk: 120 ms sampled CPU, including 30 ms in `filepath.Rel`; about
 33.55 ms runtime-trace syscall time is directory enumeration. This is a larger
  present CPU lead than Git labels. It is work on host source identity, so bypass
  or TTL caching is not a valid optimization. Instrument counts/scopes first.
* Live frontend span processing also appears (~50 ms cumulative sampled CPU in
  the indicated span-export path). These samples overlap call stacks and must
  not be added to the categories above without a disjoint call graph partition.

`overlay.json` adds opt-in `_DAGGER_CLI_TIMING_DIAG` diagnostics for actual elapsed
label loading, startEngine/startSession/subscription phases and filesystem visit
counts per hashed root. It emits no paths, Git metadata or credentials. These
are instrumentation-only overlays, not a production patch, and have not yet
been built/run. The counters identify oversized or duplicate walks before
changing their scope.

A small candidate is `fs-prefix.patch`: normal `WalkDir` descendants already
have the exact cleaned root prefix, so repeated general `filepath.Rel` work can
be skipped. It falls back to `filepath.Rel` for root, relative roots and unusual
targets; it does not change filesystem reads or source invalidation. The root
`/` empty-relative corner is explicitly guarded. Frozen control and candidate
files plus overlays are adjacent. Semantic tests include prefix collisions,
relative paths, filesystem root, trailing separators, actual subtree walks,
symlink stat behavior and Windows volume fallback. The targeted semantic suite
passed on Linux on 2026-09-25 (`go test -overlay=fs-prefix-candidate-overlay.json
-run 'Test(RelativeWalkPath|WalkPrefixPreservesTraversalAndSymlinkStats|FilterFSPrunes)'
./internal/fsutil`); Windows-only assertions were skipped. This is a constant-factor
proposal, not an established wall-time gain.
