# Warm discovery audit: remove a needless module boundary

September 25, 2026. The complete listing on greetings-api takes **2.630 → 2.546 s**
in an eight-pair warm comparison after a small Go-module change. This is about
**84 ms / 3.2%**; it does not establish 500 ms or faster edit latency. Six of eight
pairs favor the candidate; the median paired difference is 85 ms.

## Change

In Kyle's Go module at 1784ff37eb3dd1aacab7aaff91b1d86e311cc8de,
`GoMod.nestedRoots` calls `gomod.workspaceRootPath` once for every root it finds.
The explicit `gomod` receiver crosses GraphQL and starts another Dang module
invocation merely to split/join path strings. The current profile contains
three of these calls while discovering three Go modules.

A file-private `resolveWorkspaceRootPath(cwd,path)` now holds that pure logic.
Both `Gomod.modules` and `GoMod.nestedRoots` read the workspace cwd once and
call it locally. The public `Gomod.workspaceRootPath(ws,path)` delegates to it,
preserving its signature and behavior. There is no new result cache, lookup
TTL, persistent source index, helper binary, scanner, or dependency.

Unqualified `workspaceRootPath(...)` inside Gomod already ran locally. The
expensive calls were the explicit `gomod.workspaceRootPath(...)` from GoMod;
the candidate was revised before benchmarking to address that actual boundary.

This removes an O(R) count of module-runtime crossings for R nested-root
results. It does not change the asymptotic string/path computation or remove
all scanning. Public root discovery and file ownership still follow Dagger
workspace reads and invalidation. The helper only processes the values those
reads produce.

## Measurement boundaries

The app is greetings-api 14d684fccf75a137de96f3f0c7eb8c6dafef2d3e. Both sides
copy the existing complete experimental greetings-split workspace and replace
only modules.go with a local clone of the same Kyle module. Thus the absolute
numbers must **not** be compared directly with the untouched remote-module 2.662 s.
The existing backend base, Playwright service, generators and cache policies
remain present. Both local module trees come from the exact same commit.

The engine is the retained 512-payload build on
`dagger-engine.collections-disk-abba-2`, using the complete experimental stack
(Dang syntax cache, split TypeScript imports, prebuilt TypeScript runtime,
Node/tsx caches and direct Node loader). The engine binary checksum is in
module-manifest.json. The module fix itself does not require these prototypes.

Every timed sample starts a fresh CLI and executes `dagger check -l --all`,
with telemetry enabled and process exit included. Two warmups per local
variant precede eight alternating/reversed pairs. No builds, other engine
workloads or profiler run during the warm series. Host full I/O stall per
measured warm command is at most 6.6 ms. All 14 output rows match independently
recorded expected bytes. Exact SHA:
`c5ab5a8e1e456367b3c15e934d3d6fd7d62b315967d8d7c9571a24b2bbde63d6`.

| Warm | Original local module | Local normalization |
|---|---:|---:|
| Median, 8 runs |2.6304 s|2.5464 s|
| Range |2.5233–2.7786 s|2.4784–2.7618 s|

## Real edits and correctness

Each edit is written before immediately launching the same complete command.
These are single observations, not medians; the candidate does not demonstrate
an edit speedup. Independent expected output verifies that a rename removes
the old key and includes the new key.

| Edit | Before | After |
|---|---:|---:|
| Comment, unchanged keys |2.5473 s|2.7386 s|
| TestFormatResponse→TestFormatResponze |2.6530 s|2.6644 s|
| Restore source |2.6675 s|2.6417 s|

The existing gomod e2e `discovery-check` and `lookup-check` both pass against
the candidate. They cover discovery from the workspace root, nested cwd,
nearest enclosing root spelled `..`, content include/exclude and mounting the
resolved module source. Their 111.6 s execution is a correctness run involving
scanner-backed assertions and is not a performance sample. No application
checks beyond those focused library checks were run here.

Both app sources were restored byte-for-byte. The candidate module's only
source diff is gomod/main.dang (16 added / 8 removed lines). Engine 6172 is stopped;
its persistent volume remains. All work is isolated under this lab directory,
with no edits to the shared Dagger source checkout.

## Separate wcprof evidence

Both captures report zero dropped events and zero open operations. Durations
below are separate individual captures, not medians and not additive savings.

| Profile observation | Before | After |
|---|---:|---:|
| Operations |21,415|21,229|
| Engine trace span |1.750 s|1.733 s|
| workspaceRootPath invocations |3|0|
| workspaceRootPath aggregate wall |56.0 ms|0|
| Dang runSource passes |21|18|
| Gomod.modules wall |224.2 ms|163.6 ms|
| Go.modules wall |281.0 ms|223.6 ms|
| Workspace.findRoots invocations |7|7|

The underlying work reduction is confirmed even though other phases vary and
the observed whole engine span drops only 17 ms in these two particular captures.
The unprofiled eight-pair series is the source of the 84 ms median improvement.

## Existing discovery commits: keep or rework

SDK definition caching and static SDK entrypoints operate upstream of this
layer: they provide module definitions. These changes determine how the CLI
projects those definitions and how runtime collection receivers expand.
They remain complementary, rather than alternative caches of the same work.

| Change | Recommendation | Reason and invariant |
|---|---|---|
|70afe1641e, CLI bulk metadata and one discovery session |Keep; API packaging can be reviewed separately |It retains a static selection ID only inside one command and projects listing strings in one internal JSON value. It avoids per-string DagQL result/telemetry overhead and avoids a preliminary session for dynamic list commands. Collection receivers remain deferred until the filtered runtime selection. Public object APIs stay available. Review the internal snapshot field name/compatibility as API design, not as a reason to reintroduce per-row engine results.|
|b58e794fe9, dimension indexes and shared expansion prefixes |Keep |An immutable selection-local name index avoids repeated dimension scans; prefix tries replace all-pairs ancestor search. Shared expansion is request-local and keyed by schema-node identity plus workspace result, so the same receiver is enumerated once per request. No key/error survives into another request. Complexity improves with artifact count; output expansion itself remains proportional to the selected key product.|
|e6200c7b3f, parallel independent expansion |Keep, with bounded-admission follow-up |Independent templates and parent receivers run concurrently while slot-indexed outputs preserve deterministic order. Failure cancels siblings and waits before returning. Current fan-out is unbounded; huge collections can create many goroutines/runtime invocations. Limit only independent receiver execution or schedule ready DAG nodes. A semaphore held through recursive expansion can deadlock shared-prefix waiters, so a blanket outer limit is not a safe fix.|
|Current pure path helper |Upstreamable small module patch after author review |Same public API/path semantics, fewer self-call boundaries, existing nested-cwd tests pass. Warm benefit measured; no edit/cold claim.|

## Other remaining walls

1. The previous complete remote-module profile still has two overlapping Node
   registration processes around 750 ms each. SDK definition caching/static
   entrypoints remove a larger class of work than tuning artifact index maps.
2. Configured `base="dag://backend/go-test-base"` resolves eagerly while
   constructing Go. The profile contains two backend runtime calls before
   Go.modules, even though listing needs no base contents. `ModuleFunction`
   dynamic argument resolution requests the concrete object ID before call
   lookup. Deferring this requires normal typed DagQL lazy values/provenance,
   preserving errors, caller authority and cache policy. Replacing Container
   with a string setting or omitting the base would change the user's contract.
3. Seven anonymous Git advertisements are already singleflight-cached per
   session and retain their refs for later metadata access. The existing
   duplicate-transfer fix is working. A cross-session URL/TTL cache would
   change visibility/credential freshness. Pinned sources still incur the
   current eager visibility boundary; separating source availability from
   credential acquisition is architectural work, not a safe one-line cache.
4. Workspace.findRoots.descendantRoots copies marker files into a Directory
   and then globs names. That hashes/materializes contents when only names
   are required. A names-only path using the existing workspace enumeration
   protocol could help both cold and warm across languages. It must preserve
   relative paths, exclude pruning, overlays/mount shadowing, symlinks and
   returned order. No patch or timing is claimed for that idea yet.
5. The original Batch grouping used slices.Contains on accumulated keys, an
   O(K²) membership term. Commit 627f60eb28 now scans at most eight distinct
   keys before creating a request-local membership set. The final matched
   series measures 172.196 → 16.182 ms at 10,000 keys, with unchanged singleton
   allocations. CollectionBatchType is still recomputed per item; request-local
   memoization could avoid repeated metadata selections. Neither observation
   explains seconds on this metadata-only 14-row listing.
6. The Go module still insertion-sorts files O(F²), and test name extraction
   performs a file×search-match join. A bulk group/index constructor or native
   ordered sort avoids those terms; building Dang's immutable map with one
   `with` per entry currently copies the map repeatedly and retains O(N²).

The wcprof analyzer's final-root what-if result is not a whole-command latency
prediction here. Consecutive HTTP requests appear as independent roots with
recorded start offsets; optimizing an earlier root does not automatically
move later roots in that replay. Follow actual phase boundaries and validate
full-process timing after changing the work.

## Files

- module-cwd.patch: complete module source patch.
- module-manifest.json: source pins, source hashes and restoration proof.
- benchmark.py: reproducible local-ref matched driver.
- measured/results.json,summary.json: every warm/edit/profile timing.
- measured/profile-summary.json: compact wcprof evidence.
- measured/profile/{before,after}/runs.wcprof: raw profiles.
- measured/qa.json,qa.stderr,qa.stdout: exact correctness command and results.

## Completed large-collection improvement

Commit **627f60eb28** contains the final lazy batch-key membership index and
focused correctness/benchmark coverage. It preserves the bounded slice scan
for at most eight unique keys, then promotes to a request-local set while
retaining first-seen order. The expected membership term is O(K) overall,
with O(K) extra temporary memory for larger groups.

`batch-index-lazy/report.md` contains the final eight-pair series, source and
binary provenance, reproduction, and threshold/immutability test details.
Full Batch medians are **172.196 → 16.182 ms** at 10,000 keys (10.64×),
**2.991 → 1.609 ms** at 1,000 keys, and **1.551 → 1.560 µs** at one key with
identical bytes/allocations. Ten keys still cost +0.673 µs at the promotion
boundary. Focused artifact/collection tests pass on both binaries.

The earlier eager-set prototype and its distinct measurements remain under
`batch-index/`; their data are not mixed with the final lazy-index series.
These changes have been compiled, tested, benchmarked and committed in the
shared engine checkout, unlike the isolated module-path helper above.
**No greetings-api listing or edit improvement is attributed to batching:**
metadata-only listing does not traverse the Batch evaluation phase.
