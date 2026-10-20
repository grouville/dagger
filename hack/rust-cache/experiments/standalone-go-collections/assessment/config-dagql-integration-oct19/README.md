# Integrated DagQL cache: verification and limits

The draft now uses the existing `dagql.Cache.GetOrInitArbitrary` API for derived Git-client declarations. The helper is 40 lines rather than the LRU version's 49. There is no global LRU, custom entry limit, size threshold or OnceValue wrapper. It obtains engine cache/session context when available and otherwise parses normally. Cache errors also fall back to pure parsing. The shared configuration package now imports DagQL and engine metadata; this avoids a separate cache adapter/API but is a new package dependency. The full PR is approximately the same size because tests need cache/session setup.

Live reads and nearest-config selection remain outside the cache. Current content determines the key; scope selection, per-caller warning delivery and cloned return slices preserve behavior. Entries can be shared across concurrent commands and are removed after their last owning session finishes. They have no fixed 32-entry bound and are not retained across non-overlapping commands. This is an in-memory metadata cache, not persisted build output.

Candidate and main `ce6dc9f9403b52067f5831149eab4871f857185d` pass the complete workspace race suite with identical added behavior tests. The candidate race log is recorded separately before the verification driver, which runs the main race suite once and builds both benchmark binaries. The source manifest matches the tested candidate and amended PR worktree byte-for-byte. Matching static engines and CLI build successfully. No other heavy build or benchmark overlaps the measurements.

Four alternating fresh-process component pairs, 5,000 lookups per process, GOMAXPROCS=8, actual 1,649-byte Go configuration:

| Complete declaration lookup | Main | DagQL version | Allocations |
| --- | ---: | ---: | ---: |
| Repeated current contents | 343.553 µs | 5.2225 µs | 2,818 → 9 |
| Repeated contents, concurrent callers | 153.6555 µs | 3.414 µs | 2,818 → 9 |
| New contents on every lookup | 342.6935 µs | 387.8815 µs | 2,823 → 2,840 |

Both repeated-content cases improve in all four pairs. Distinct content is slower in all four pairs, about 13.2% by median. Concurrent results are time per completed lookup across eight workers. Cache setup and teardown are outside timing. These replace the old LRU component figures for the current draft.

The fresh-CLI integration comparison uses one root Go module with 16 packages and 16 tests, fixed module configuration, unique test renames plus source edits on every invocation, and two separately retained engines built on the same current-main base. It keeps ordinary telemetry, cache policy and GC. Four initialization commands and eight measured commands return the expected ordered rows and exit successfully through cleanup. The four measured pairs are **inconclusive for performance**: main 6.657 s versus candidate 6.831 s, candidate faster in only one pair. Engine CPU medians are 26.139 versus 26.474 CPU-seconds; allocated bytes are 3.735 versus 3.911 GB. Commands vary between roughly four and ten seconds. Do not publish this as an end-to-end win, discard slower samples or reuse the older LRU full-listing figures as this implementation's result.

A separate diagnostic observes a real `workspace.gitClientDeclarations` value in the engine's completed arbitrary cache, with one session owner. The key contains SHA-256 `ce4c1322b74d0c8fe5d8536794979cc6fef7aae2e8064f566cf73f2b8f87bdcd`, matching the actual Go module's dagger.toml. A post-command snapshot contains no declaration entries and no active sessions. These snapshots are excluded from benchmark timings. The first two diagnostic snapshots occurred before the query owned cache entries; they are retained as attempts rather than treated as evidence that caching failed. The final observation samples through the command until the entry appears.

Tests cover changed and deleted files, nearer configurations, invalid/unreadable data, caller mutation, concurrent readers and warnings on each caller. Existing no-engine-context tests also pass. DagQL's existing lifecycle/concurrency tests cover its implementation; no duplicate cache-algorithm test is added to the PR.

The earlier LRU implementation reduced a full 4,398-row listing on an experimental engine. That motivated this work, but those times do not measure this final DagQL-backed patch. A stable independent full-command improvement remains unproven. Raw checks, all component/integration samples, source patches, static build identities and filtered cache-entry reports accompany this report. Full cache snapshots remain in the shared local experiment directory; their hashes are recorded separately because the entry reports are sufficient for review. Existing engines and volumes remain untouched.
