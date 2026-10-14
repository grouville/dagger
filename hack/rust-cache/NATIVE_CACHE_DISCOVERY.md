# Recover native Rust state through ordinary checks

An isolated engine and Rust module prototype now recover the previous compiler
cache automatically. With `nativeCache = true`, ordinary `dagger check rust:check`
captures its initial compiler plan, publishes the successful native cache, and
uses that cache on the next source edit. Callers supply neither a compiler plan
nor a previous cache object. Compiler artifacts, plan and incremental state stay
native Dagger objects.

The engine index holds the original native result through the existing ownership
API. Lookup claims the result for the reading session through the normal loader,
including its resource checks. Temporary ownership protects a lookup from
concurrent replacement; replaced and evicted entries release their holds. The
prototype retains at most 128 keys and clears its holds during shutdown.

Keys use the module's existing cache namespace and the project's `cacheKey`.
Use distinct keys for different projects. Reads and writes run on every call,
and the module publishes only after compilation and output materialization
succeed. Selected state remains an explicit compilation input. Compiler result
and seed compatibility checks are unchanged.

This is an engine-lifetime prototype. The index does not survive restart or
discover state on another engine automatically. Its entry count is bounded;
retained bytes and dependency ancestry are not yet measured or bounded by a
storage policy. A retained cache object may also keep earlier computation
dependencies alive. Persistence, pruning and remote discovery need further
design before selecting this API for the official module.

## Verification

- Focused ownership and schema tests pass under the race detector. They cover
  session closure and pruning, replacement and dependency release, invalid
  publication, bounded eviction, shutdown, concurrent reads, and repeated
  mutable API reads and writes. The new fields are hidden from older API views.
- Separate client sessions reuse 3/4 actions after real source edits without
  creating or reading a metadata directory. Invalid Rust fails; the next valid
  edit still reuses 3/4. A configuration edit recaptures with 0/4 reuse, followed
  by 3/4 on the next source edit.
- The ordinary workspace check passes. Its output can then be recovered by a
  separate API session with 4/4 reuse.
- Explicit native cache transfer still reuses 4/4 actions on an independent
  engine, then 3/4 after an edit. The writer's plan, new-target, unsupported
  build-script and invalid-configuration checks also pass.

The benchmark branch's base-schema allowlist check still fails on its existing
`Directory.digest(path:)` experiment. This prototype does not alter that field;
its own API visibility test passes.

An initial ordinary CLI fixture omitted the Git boundary present in the earlier
fixture. Its source import expanded unexpectedly and was interrupted after a
goroutine capture. Establishing the fixture's Git root corrected the import;
the engine drained back to 26 goroutines. This setup failure is excluded from
timing and remains a separate workspace-boundary concern.

## Edited complete commands

Five alternating samples per scenario use the ordinary `dagger check` command,
fresh client processes and unique host edits. Images, tools and compiler state
are warm. Cargo uses the matching Rust 1.77.2 toolchain, a separate source tree
and target, and incremental compilation. Three shared/leaf preparation rounds
precede timing. Telemetry stays enabled to the local receiver; wcprof is off.

| 102-action workspace | Ordinary native check | Cargo |
| --- | ---: | ---: |
| Leaf edit, median | 0.910 s | 0.089 s |
| Shared edit, median | 1.423 s | 0.486 s |

All Cargo logs rebuild the expected two or 102 crates. After each timed native
command, an untimed fresh API session recovers its output with 102/102 reuse.
Those probes prove that the ordinary command published usable state, not the
number of reused actions inside the timed command. Maximum timed CPU/I/O
pressure is 25.3%/2.2%. This is a workflow measurement, not a matched speedup
claim. Both scenarios still exceed Cargo +0.5 seconds.

One subsequent shared-edit profile records zero dropped events and no open
operations. Its 1.37-second critical path includes:

| Exclusive contribution on the path | Time |
| --- | ---: |
| Compiler worker workload | 459.9 ms |
| Go helper's own workload | 80.0 ms |
| Query handling across sessions | 155.4 ms |
| Check execution outside recorded nested work | 135.8 ms |
| Artifact/state snapshot copying | 124.6 ms |
| Host directory imports | 67.2 ms |
| Creating the two containers | 24.9 ms |

These contributions are from one profile, not medians or a complete breakdown.
The helper's inclusive workload contains the compiler worker. The hint lookup
takes 44.5 microseconds; publication takes 3.46 ms including its object load.
They are not the dominant remaining costs. The next experiments should target
module/query execution and filesystem preparation before adding process reuse.

Engine: [experiment/native-cache-hints](https://github.com/grouville/dagger/tree/experiment/native-cache-hints).
Rust module: [experiment/native-cache-hints](https://github.com/grouville/dagger-rust/tree/experiment/native-cache-hints).
Local artifacts under `/tmp/rust-cache-sipsma-review`: `module-native-hints`,
`module-native-hints-102`, `native-hints-transfer-*`, `verify_native_hints.py`
and `measure_native_hints_102.py`.

The full goal remains open: persistent and remote state discovery, retention
and transfer costs, real dependencies, build scripts, procedural macros and
tests, and further latency reductions through the official module.

## Automatic discovery after restart

A separate engine experiment now saves the bounded latest-result index in the
same SQLite transaction as the native cache graph. It preserves the existing
module/project namespace and LRU order, with at most 128 keys. The Rust module
code is unchanged: the selected cache fields still become ordinary explicit
compilation inputs.

At checkpoint, clean hint values without session-resource requirements acquire
ordinary prunable cache roots. Shutdown saves those values before releasing the
index's memory holds. Restored lookup metadata does not pin unused values;
pruning a referenced value becomes an acceleration miss and removes the stale
lookup. Values requiring a session resource are excluded from this index's
durable checkpoint. Existing resource checks still apply when loading values.

A focused restart test fails on the original implementation and passes with
the prototype. Race checks cover repeated reopenings, latest publication,
namespace separation, values without an existing persistence root, bounded LRU
restoration, pruning of unused restored values, session-resource exclusion and
the existing concurrent replacement/read and persistence behavior.

The actual Rust module runs without supplying a plan, manifest, cache IDs or
previous-cache argument from the test driver:

| Action | Reused compiler results |
| --- | ---: |
| First check | 0/4 |
| New app edit | 3/4 |
| Restart engine, then check | 4/4 |
| New app edit after restart | 3/4 |

The ordinary `dagger check rust:check` entrypoint also passes. A new process
recovers its published state with 4/4 reuse after engine restart, and an edited
ordinary check publishes state recoverable with 4/4 reuse. No cache metadata is
saved outside the engine. An initial probe ran from the project directory while
its driver expected the Rust module directory; that failed before loading the
module and is excluded from the corrected check.

Twenty unique edits each reuse 3/4 results. After pruning at edits 5, 10 and 20,
the latest cache's closure stays at 307 results and 59 distinct snapshot
references; each subsequent check reuses 4/4. No mutual ownership cycles appear.
Evicting all project hints and fully pruning removes every Rust compilation and
cache object. These figures describe retained graph references, not unique
physical bytes or remote transfer costs.

This remains an isolated prototype. It establishes automatic recovery after a
clean engine restart, not crash durability or remote latest-state discovery.
Checkpoint cost and complete edited-command latency have not been compared for
this change. The namespace policy, promotion of hint roots and concurrent
checkpoint/resource changes still need review before adopting a general API.
Registry dependencies, build scripts, procedural macros and tests remain outside
the supported experimental subset.

Engine branch:
[experiment/persistent-native-cache-hints](https://github.com/grouville/dagger/tree/experiment/persistent-native-cache-hints),
commit `ba5861200`, based on `86c94a5d9`. The module is the unchanged checkpoint
branch at `d1aaf93`. Artifacts under `/tmp/rust-cache-sipsma-review` include
`persistent-cache-hint-*-race.log`, `persistent-cache-hint-repro.log`,
`persistent-hints-module-*.log`, `persistent-hints-normal-cli-*.log`,
`persistent-hints-retention` and `check_persistent_hints_retention.py`.
