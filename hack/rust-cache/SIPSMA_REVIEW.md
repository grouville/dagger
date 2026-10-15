# Engine performance references

Initial review: 2026-10-13; follow-up below: 2026-10-14. Goal: [native Rust cache performance](ROADMAP.md).

The public GitHub search for `repo:dagger/dagger is:pr author:sipsma` returned
935 PRs. The inventory was scanned for performance, cache, filesync, runtime,
telemetry and profiling changes. Bodies of 67 related PRs were fetched, including
the six original performance PRs and their subsequent work. File diffs were
fetched for 42 of them, with the relevant production paths inspected. This is
not a claim that every historical PR's code was reviewed.

Our measured engine starts at upstream
`f9d7e23a32723427178b6d09ed8d75de6cc3cafd`, plus the experimental snapshot owner
index and directory digest path. Current upstream at the time of this review was
`7f375c14f27256c91103ca0bb84421fc33a963d7`. Merge ancestry was checked locally
rather than assuming that a closed PR was merged or that an upgrade would supply
a change already in our baseline. Raw inventory, PR bodies and diffs are saved
under `/tmp/rust-cache-sipsma-review`.

## What to test next

1. **Keep telemetry and reduce its work.** [#14626](https://github.com/dagger/dagger/pull/14626)
   avoids encoding and validating span attribute lists twice.
   [#14627](https://github.com/dagger/dagger/pull/14627) avoids cloning a call's
   entire recipe to read its output digest and type. Both are unmerged and absent
   from our baseline. Their combined edited Go result is suggestive: the ranges
   overlap, so it is not an established Rust speedup. Test them together on the
   existing Rust fixture before attributing a gain to either one.
2. **Refresh the engine reference separately.** New merged changes include
   [#14653](https://github.com/dagger/dagger/pull/14653), which removes synchronous
   stderr writes from most logging calls, and
   [#14610](https://github.com/dagger/dagger/pull/14610), which lets archive readers
   proceed while an existing manifest is written and synced. The latter could
   matter under disk load; it does not prove the cause of our earlier shutdown
   outlier. Compare current main against the pinned reference without mixing
   that comparison with a new Rust backend change.
3. **Keep attacking the snapshot copies.** The latest Rust shared-edit capture
   has one 650 ms compiler workload and two directory copies with about 261 ms
   of summed own time. Concurrent work and waits overlap, so this is not 261 ms
   of removable command latency. Source digest queries already bypass package
   projection results; input-state and retained-history copies remain. A local
   copier experiment reuses resolved parents for directories as it already does
   for files. Six interleaved microbenchmark runs show roughly 6% less time and
   11% fewer allocations; full edited-build benefit is still unmeasured.
4. **Measure crun with realistic expectations.**
   [#14607](https://github.com/dagger/dagger/pull/14607) reduces per-container
   startup substantially in Sipsma's measurements. Our batched Rust backend has
   one compiler container per edited build, with about 39 ms runtime startup in
   the latest capture. It cannot save one startup per crate in that design.
5. **Measure module startup when integrating the backend.**
   [#14608](https://github.com/dagger/dagger/pull/14608),
   [#14649](https://github.com/dagger/dagger/pull/14649) and
   [#14631](https://github.com/dagger/dagger/pull/14631) target nested sessions,
   Dang execution and typedef loading. Our standalone compiler replay bypasses
   these paths. They need a separate module-level comparison.

The standalone replay still builds against this experiment branch's older Go
SDK. Its generated `ID()` methods issue a query unless the object was constructed
with an ID; they lack #14593's memoization. Having that PR in the engine baseline
does not upgrade this caller. A separate SDK migration and comparison is needed;
current upstream separates the transport client from the generated core query
API, so replacing the module dependency alone is insufficient.

The organization-wide scan also found
[#61 in go-sdk](https://github.com/dagger/go-sdk/pull/61), which ports the ID
memoization to that repository's client generators. It is merged, but clients
must be regenerated against a v1 schema declaring `@reevaluate` to receive the
optimization. It does not make our existing generated client faster by itself.
The subsequent [SDK comparison](SDK_COMPARISON.md) forward-ports the prototype,
passes the native transfer integration, and finds no repeatable command speedup;
the captured request count is unchanged.
The scan returned 111 PRs updated since October 1, including 13 outside
`dagger/dagger`; the other cross-repository work concerns remote-cache service
deployment, storage, telemetry and CI rather than a published `gcexp` repository.

## Published Go replay prototype

The subsequent fork-branch scan located Sipsma's prototype in
[`gocache-bench-gcexp`, commit 4ebfa5f](https://github.com/sipsma/dagger/tree/4ebfa5f6619d61fa495844c2f1bac6ef788b923f/.dagger/modules/gcexp).
The earlier organization-wide PR search did not locate this fork branch.

Its [`replay.go`](https://github.com/sipsma/dagger/blob/4ebfa5f6619d61fa495844c2f1bac6ef788b923f/.dagger/modules/gcexp/replay.go)
replays `go build -n` as one native Dagger execution per package. Each action
mounts filtered source files and native dependency archives; compiler actions
disable Dagger nesting. Module downloads are native directory outputs keyed
on `go.mod` and `go.sum`. The documented scope is Go build with cgo disabled
and no `go:embed`; this is explicitly a measurement prototype.

These choices match the Rust experiment's native inputs/outputs and disabled
compiler nesting. Our many-crate backend batches misses into one compiler
container to avoid repeated launch costs while retaining per-crate result
keys and incremental snapshots. Its layered Go alternative also seeds a
normal directory output containing external-dependency compiler state. That
is a useful model for dependency preparation, but it does not solve selecting
the latest incremental state for edited local Rust crates automatically.

The [native module follow-up](NATIVE_PROFILE_FOLLOWUP.md) records the later
crun and nonblocking-helper comparisons. These supersede the earlier "what
to test next" status for those changes; keep measurements from different
workloads and engine versions separate.

## Rust comparison of the telemetry PRs

The candidate adds Sipsma's production commits `ab042e582` (#14626) and
`1f8362374` (#14627) to the measured engine reference, retaining the owner index
and digest-path experiment. The control and candidate use the same image assets,
CLI beta.17, replay binary, Rust 1.77.2 and synthetic 102-action workspace, on
separate initially fresh engine volumes. No engine was restarted during either
series. Four preparation edits populate each bounded history before timing.

Each series alternates five before/after pairs per edit scenario and rotates
Cargo/replay order. All 40 timed fresh edits across the two series pass artifact
contents, modes, expected recompilation sets, edit-value propagation and complete
finished-result reuse checks. No history fallback occurred.

| Series | Edit | Before median (range) | With both PRs median (range) | Cargo medians before / after |
| --- | --- | --- | --- | --- |
| First | Leaf | 1.449 s (0.939–2.261) | 1.351 s (0.909–1.457) | 0.557 / 0.541 s |
| Repeat | Leaf | 0.598 s (0.578–0.652) | 0.595 s (0.568–0.618) | 0.218 / 0.217 s |
| First | Shared | 1.342 s (1.313–1.403) | 1.312 s (1.273–1.393) | 0.656 / 0.668 s |
| Repeat | Shared | 1.300 s (1.279–1.485) | 1.270 s (1.251–1.334) | 0.649 / 0.654 s |

The first leaf series had substantial CPU and disk contention; Cargo slowed too.
Its apparent 97 ms median gain did not reproduce. The shared-edit median fell
about 30 ms in both series, but ranges overlap and the samples are small. This
supports a modest local gain, not a large Rust speedup. The shared result remains
about 116 ms above Cargo + 0.5 s in the repeat.

Matched engine CPU profiles each cover eight additional fresh shared edits in a
20-second window, with no other builds or benchmarks from this experiment
concurrent. Sampled
engine CPU totals are 13.96 s before and 13.76 s after. `MarshalProtoJSONs`
cumulative sampled CPU falls from 440 ms to 230 ms. `recordCacheEvidence` is
70 ms on both sides, so this capture does not establish an additional gain from
#14627 in our workload. These are CPU samples, not removed wall-clock time.
The final profiled exports have the same 305 files, contents and modes.

Focused `engine/clientdb` and `core` regression tests pass with the race detector;
`go vet ./engine/clientdb` and the candidate engine build pass. Telemetry stays
enabled and is sent to a local receiver with a dummy token and isolated empty
client configuration. Production Cloud latency is unmeasured: automatic approval
review rejected the external telemetry export, so the comparison uses the
approved local receiver instead.

Raw timing summaries and pressure samples are in
`/tmp/rust-cache-sipsma-review/telemetry-{comparison,repeat}`; CPU profiles and
command logs are in `cpu-{before,after}` under that same review directory. The
candidate is an experiment containing existing upstream PR code, not a new
upstream fix.

Use fresh edits on populated native caches with retained Rust incremental state.
Measure the complete command, including source import, artifact export, history
retention and shutdown. Keep Cargo as the control, alternate variants, and check
the expected compiler misses and exported artifacts outside the timed interval.
Unchanged replay is a correctness check here, not our performance target.

## The original series

All six performance changes are already ancestors of our pinned engine.

| PR | Removed work | Consequence for this experiment |
| --- | --- | --- |
| [#14551](https://github.com/dagger/dagger/pull/14551) | Decode a container payload for every output; repeatedly map all mount groups. | Many mounts no longer pay this quadratic probe cost. |
| [#14553](https://github.com/dagger/dagger/pull/14553) | Copy a mount's value through every later container layer. | Delegation goes directly to the layer that wrote the part. |
| [#14555](https://github.com/dagger/dagger/pull/14555) | Walk a file's entire parent directory to checksum that file. | Reading an execution stamp does not scan the toolchain rootfs. |
| [#14556](https://github.com/dagger/dagger/pull/14556) | Misattribute lock waits and runtime startup to useful work. | Use explicit waits and nested-client critical paths when interpreting profiles. |
| [#14557](https://github.com/dagger/dagger/pull/14557) | Gather files through one snapshot layer per file. | `withFiles` already makes one copy operation; native directories avoid this gathering altogether. |
| [#14558](https://github.com/dagger/dagger/pull/14558) | Parse the complete mount table during each rootfs bind cleanup. | Rootfs cleanup already tries a single detach syscall first. |

[#14554](https://github.com/dagger/dagger/pull/14554) fixes a service detach race;
it is not a caching performance change.

## Subsequent changes

"Baseline" means already present in `f9d7e23a`. "New main" means merged after that
reference. "Open" means unmerged at review time.

| PR | Status | Mechanism and relevance |
| --- | --- | --- |
| [#14563](https://github.com/dagger/dagger/pull/14563) | Baseline | Install network rules per subnet instead of per container. Most useful beyond the ready namespace pool. |
| [#14578](https://github.com/dagger/dagger/pull/14578) | Baseline | Stop telemetry recipe walks at closures already delivered. Avoid repeated graph traversal. |
| [#14585](https://github.com/dagger/dagger/pull/14585) | Baseline | Attach snapshot owner leases outside the manager lock and in one metadata transaction. |
| [#14591](https://github.com/dagger/dagger/pull/14591) | Baseline | Repair e-graph roots after absorbing input terms. Cache correctness, rather than a demonstrated Rust speedup. |
| [#14592](https://github.com/dagger/dagger/pull/14592) | Baseline | Find equivalent results through the output-class index. Particularly relevant to restored caches. |
| [#14593](https://github.com/dagger/dagger/pull/14593) | Baseline | Memoize Go SDK object IDs while preserving reevaluation semantics. Check the caller's generated SDK too. |
| [#14594](https://github.com/dagger/dagger/pull/14594) | Baseline | Reduce metadata commits and share a mount within a small-file read. Per-call sharing was superseded by #14619. |
| [#14596](https://github.com/dagger/dagger/pull/14596) | Baseline | Avoid rebuilding session-owned typedef results on CLI startup. Relevant to the module's user-facing command. |
| [#14598](https://github.com/dagger/dagger/pull/14598) | Baseline | Separate init, command spawn, workload and exit in wcprof. Profiling, not a runtime optimization. |
| [#14603](https://github.com/dagger/dagger/pull/14603) | Baseline | Prune directory walks using reachable include prefixes. Our seed copies already have this optimization. |
| [#14604](https://github.com/dagger/dagger/pull/14604) | Baseline | Release read-only mounts in the background. Superseded at the call boundary by #14619; its release queue remains. |
| [#14605](https://github.com/dagger/dagger/pull/14605) | Baseline | Split the large nested-session helper out of the minimal init binary. |
| [#14606](https://github.com/dagger/dagger/pull/14606) | Baseline | Correct trailing-glob prefix pruning in filesync and glob handling. Preserve this behavior in filter experiments. |
| [#14607](https://github.com/dagger/dagger/pull/14607) | Open | Replace runc with crun. Profile the number of actual containers before projecting a gain. |
| [#14608](https://github.com/dagger/dagger/pull/14608) | New main | Start the user's command without waiting for the nested-session helper to register. Compiler replay disables nesting. |
| [#14610](https://github.com/dagger/dagger/pull/14610) | New main | Keep archive index lookups independent of existing-manifest fsyncs. |
| [#14616](https://github.com/dagger/dagger/pull/14616) | Baseline | Expose disk I/O, pressure and writeback metrics to distinguish computation from host contention. |
| [#14619](https://github.com/dagger/dagger/pull/14619) | Baseline | Share immutable snapshot mounts across readers and briefly retain idle views. Our earlier comparison did not establish a full Rust command gain. |
| [#14626](https://github.com/dagger/dagger/pull/14626) | Open | Append protojson elements directly into telemetry arrays. Candidate for the Rust comparison. |
| [#14627](https://github.com/dagger/dagger/pull/14627) | Open | Read immutable call-frame facts without cloning the recipe. Candidate for the Rust comparison. |
| [#14630](https://github.com/dagger/dagger/pull/14630) | New main | Expose read-only file mounts, avoiding a mutable snapshot for tools the command does not modify. |
| [#14631](https://github.com/dagger/dagger/pull/14631) | Open | Avoid session-owned `asCollection` results while keeping real collection metadata addressable. No established startup latency gain. |
| [#14649](https://github.com/dagger/dagger/pull/14649) | New main | Remove two redundant source parses per Dang function call. Measure if the Rust module uses that runtime. |
| [#14653](https://github.com/dagger/dagger/pull/14653) | New main | Queue ordinary engine log lines for background writes. Retains synchronous warnings/errors; abrupt crashes can lose queued ordinary lines. |
| [#14655](https://github.com/dagger/dagger/pull/14655) | Open | Stop and reap the nested-session helper and keep its output separate from the command. Correctness companion to #14608. |

## Other reviewed references

Telemetry and lifecycle:
[#13697](https://github.com/dagger/dagger/pull/13697) bounds idle log-batch allocation,
[#14303](https://github.com/dagger/dagger/pull/14303) forwards telemetry from the engine,
[#14381](https://github.com/dagger/dagger/pull/14381) adds cache telemetry,
[#14385](https://github.com/dagger/dagger/pull/14385) leaves eligible final Cloud delivery to the existing forwarder,
[#14406](https://github.com/dagger/dagger/pull/14406) avoids unnecessary workload-export allocation and sampling,
[#14535](https://github.com/dagger/dagger/pull/14535) retains attachables for the final flush,
[#14539](https://github.com/dagger/dagger/pull/14539) attaches network accounting hooks once,
[#14544](https://github.com/dagger/dagger/pull/14544) mounts the engine CLI into nested containers, and
[#14597](https://github.com/dagger/dagger/pull/14597) repairs dropped telemetry payloads.
These paths explain why removing telemetry is not the right default optimization.

Cache storage and locking:
[#14313](https://github.com/dagger/dagger/pull/14313) samples usage outside the graph lock,
[#14390](https://github.com/dagger/dagger/pull/14390) prepares remote merges before locking,
[#14435](https://github.com/dagger/dagger/pull/14435) leases reused import snapshots,
[#14469](https://github.com/dagger/dagger/pull/14469) accounts for large cached payloads,
[#14470](https://github.com/dagger/dagger/pull/14470) reclaims released snapshots,
[#14480](https://github.com/dagger/dagger/pull/14480) persists blob-backed caches,
[#14482](https://github.com/dagger/dagger/pull/14482) avoids repeated merge validation, and
[#14518](https://github.com/dagger/dagger/pull/14518) permits on-demand class compaction.
[#14388](https://github.com/dagger/dagger/pull/14388) is the remote cache protocol.
[#14241](https://github.com/dagger/dagger/pull/14241) is an unmerged integration fixture;
[#14508](https://github.com/dagger/dagger/pull/14508) is an empty dogfood trigger, not a Go compiler-cache prototype.

Older performance context:
[#13393](https://github.com/dagger/dagger/pull/13393) and
[#13588](https://github.com/dagger/dagger/pull/13588) establish wcprof and its reporting;
[#13124](https://github.com/dagger/dagger/pull/13124) restores batched directory-chain materialization;
[#13117](https://github.com/dagger/dagger/pull/13117) reduces bbolt metadata overhead;
[#11799](https://github.com/dagger/dagger/pull/11799) and
[#10967](https://github.com/dagger/dagger/pull/10967) reduce module loading and introspection work;
[#11709](https://github.com/dagger/dagger/pull/11709) changes image decompression;
[#11497](https://github.com/dagger/dagger/pull/11497) uses hardlinks for copies;
[#11401](https://github.com/dagger/dagger/pull/11401) and
[#10965](https://github.com/dagger/dagger/pull/10965) cover earlier engine and telemetry optimization;
[#8818](https://github.com/dagger/dagger/pull/8818) improves filesync.
[#11919](https://github.com/dagger/dagger/pull/11919) is explicitly an untested gRPC tuning draft.
[#5400](https://github.com/dagger/dagger/pull/5400) is historical BuildKit MergeOp work;
it is not evidence about the active native engine path.
[#14368](https://github.com/dagger/dagger/pull/14368) persists module typedefs and
[#14450](https://github.com/dagger/dagger/pull/14450) reduces Go dependency downloads;
their direct relevance is module startup and CI, respectively.

## October 14 follow-up

[#14685](https://github.com/dagger/dagger/pull/14685) removes the final whole-filesystem
sync from graceful engine shutdown. Its reproduction shows why a shared busy
filesystem can delay engine stop even after the engine has closed its stores.
It also states the durability tradeoff: a host crash before writeback can lose
or corrupt state after a nominally clean stop. Ordinary process restart on the
same kernel still sees the page cache. Our edited-command comparisons keep the
engine running, so this shutdown change is not a candidate explanation or
speedup for those commands. Its bounded kernel and cgroup diagnostics are a
useful model for attributing I/O waits.

[#14688](https://github.com/dagger/dagger/pull/14688) fixes an agent's exit-time
archive lookup racing its first control record. On a miss, it drains pending
agent control publications and flushes session telemetry before checking again.
The real-session regression and deterministic publisher-barrier test exercise
that ordering. This concerns agent resume; it does not remove work from the
Rust compilation path.

Both were open when checked through GitHub on this follow-up. Neither is
applied to claim a Rust performance improvement.

The subsequent check also covers
[#14687](https://github.com/dagger/dagger/pull/14687), which reserves the
unanswered test server's port so another test cannot answer the reachability
probe, and [#14686](https://github.com/dagger/dagger/pull/14686), which skips the
Homebrew refresh during macOS Docker provisioning. Both concern test or CI
setup and leave the Rust edited-command path unchanged.

## Method to carry over

Look for work that grows with the entire graph when only a small part changed:
repeated payload decoding, ancestor traversal, recipe cloning, filesystem scans
and global-map scans. Share immutable work, batch related metadata writes and
move slow I/O out of locks when lifecycle and crash consistency permit it.

For each candidate, demonstrate the expensive path, preserve results and errors,
test the failure or concurrency boundary, then measure fresh edited commands.
Report microbenchmark and CPU gains separately from end-to-end latency. Do not
add concurrent durations or count one shared exec twice when several requests
wait on it.
