# Filesync Incremental Materialization: Complete Review Guide

This doc is the one-stop narrative for the current branch.
Use it to explain:

1. What we were doing before.
2. What we do now.
3. What options were considered.
4. What we chose and why.
5. How layer/parent-depth limits are handled.
6. How to navigate the code quickly during review.

## 1) TL;DR

Before:

1. Sync updated a mutable mirror.
2. Output materialization often copied a large tree again on misses, even for tiny edits.
3. Identity reuse mainly depended on contenthash search after checksum.

Now (this branch):

1. Same mirror/diff logic stays.
2. We compute a stable filesync scope key and keep a per-scope head.
3. We try direct root-digest index reuse first.
4. On materialization misses, we can build from previous scope parent and copy only changed paths (+ required ancestors).
5. Parent chain depth is capped to prevent unbounded chaining.

## 1.1) Start from API (where people already are)

Most reviewers first think in API calls, not cache internals.
Use this one boundary diagram first (control + data flow together).

Key code references:

1. API entry: `core/host.go:112-142`
2. Filesync entry: `engine/filesync/filesyncer.go:93-213`
3. Snapshot commit/finalize: `engine/filesync/localfs.go:959-1070`
4. Directory holds snapshot: `core/directory.go:41-68`
5. Generic read/consume path: `core/util.go:588-608` and `core/util.go:278-346`
6. Container mount consumption: `core/dagop.go:512-517` and `core/container_exec.go:243-275`

Plain-language boundary model:

1. User + CLI/SDK client run outside the engine.
2. `host.directory(...)` call enters engine API (`core.Host.Directory`).
3. Engine filesync builds an immutable snapshot and returns a `Directory` that points to it.
4. Later API calls (directory reads, container mounts/exec) consume that snapshot inside the engine.
5. Bytes go back to host only on explicit export/write operations.

```d2
direction: down

outside: {
  label: "Outside engine (user machine)"
  shape: rectangle
  style: {
    fill: "transparent"
  }
  user: "User code / command"
  client: "Dagger client process (CLI / SDK runtime)"
  host_fs: "Host filesystem"
}

inside: {
  label: "Inside engine"
  shape: rectangle
  style: {
    fill: "transparent"
  }

  api: "core.Host.Directory resolver"
  fsync: "FileSyncer.Snapshot"
  mirror: "Mutable mirror (engine-local)"
  snapshot: "Immutable snapshot ref (engine-local)"
  dir_ops: "Directory/File operations"
  ctr_ops: "Container mounts + exec"
  export_op: "Explicit export/write op"

  api -> fsync -> mirror -> snapshot
}

stream: "Session stream (diff/stat/file data)"

outside.user -> outside.client: "calls host.directory(...)"
outside.client -> inside.api: "API request"
outside.host_fs -> stream -> inside.mirror
inside.snapshot -> inside.api: "Directory.Result points here"
inside.api -> outside.client: "returns Directory handle"
inside.snapshot -> inside.dir_ops
inside.snapshot -> inside.ctr_ops
inside.snapshot -> inside.export_op -> outside.host_fs
```

## 1.2) Visuals (with timing split)

This section is meant to be told as a story, not as isolated diagrams.
All visuals below are D2-only for consistency.

Story order:

Use `1.1` as the intro, then this order:

1. Before path (why it is slow).
2. Now path (what changed and what improves).
3. Scope key (why reuse is safe and isolated).
4. Depth cap/rebase guardrails.
5. Future tree-CAS.

### Story Beat 1: Before path (`main`) - why it can feel like reupload

What to say:
1. Host-to-engine transfer and mirror update are correct.
2. The expensive part is usually output materialization on misses.
3. It can look like "reupload everything" because the output copy set stays broad.

```d2
direction: down

before: {
  label: "Method 1 (main baseline)"
  step1: "1) Receive host changes and apply them to mirror"
  step2: "2) Compute filesystem checksum"
  step3: "3) Try content reuse lookup"
  hit: "Hit: return existing immutable output"
  miss: "Miss: create new output from empty base"
  step4: "4) Copy a broad path set (includes unchanged paths)"
  step5: "5) Commit + finalize -> new immutable output"
  note: "Result: small edit can still trigger large copy_data work"

  step1 -> step2 -> step3
  step3 -> hit: "reuse found"
  step3 -> miss: "reuse not found"
  miss -> step4 -> step5 -> note
}
```

### Story Beat 2: Now path (current branch) - what changed

What to say:
1. We did not change API behavior.
2. We changed how output is built after diff/apply: reuse the latest snapshot for the same sync scope when safe, then copy only changed paths.
3. There are two different reuse mechanisms:
4. Digest lookup (root index, then contenthash) asks: "do we already have this exact final content?"
5. Scope key/head asks: "if we must build, what previous output is safe to use as parent?"
6. "Broader equivalent-content lookup" means digest reuse is global (not restricted to one scope key).

```d2
direction: down

now: {
  label: "Method 2 (current branch)"
  step0: "0) Build sync scope key and load per-scope head"
  step1: "1) Receive host changes and apply them to mirror"
  step2: "2) Compute filesystem checksum"
  step3a: "3a) Try root-index lookup by checksum (exact content)"
  step3b: "3b) If miss, try global contenthash lookup (exact content across any scope)"
  hit: "Hit: return existing immutable output"
  miss: "Miss: build a new output snapshot"
  step4: "4) Choose base: previous scope head ref (if depth < 128), else empty base"
  step5a: "5a) Remove deleted paths"
  step5b: "5b) Copy changed paths only (+ required parent folders)"
  step6: "6) Commit + finalize -> new immutable output"
  step7: "7) Save scope head + checksum index"
  note: "Result: small edits usually avoid broad copy_data rematerialization"

  step0 -> step1 -> step2 -> step3a -> step3b
  step3a -> hit: "exact lookup hit"
  step3a -> step3b: "exact lookup miss"
  step3b -> hit: "global digest lookup hit"
  step3b -> miss: "global digest lookup miss"
  miss -> step4 -> step5a -> step5b -> step6 -> step7 -> note
}
```

Before vs now, in one glance:

```d2
direction: down

same_start: "Same scenario: tiny host change in large context"

before_view: {
  label: "Method 1 (main baseline)"
  b1: "copy set often broad (changed + many unchanged paths)"
  b2: "copy_data dominates (example: ~3200-3800 ms)"
  b1 -> b2
}

now_view: {
  label: "Method 2 (current branch)"
  n1: "copy set reduced to changed paths (+ required parents)"
  n2: "copy_data shrinks a lot (example: ~2-3 ms)"
  n3: "diff_apply becomes the dominant remaining cost"
  n1 -> n2 -> n3
}

same_start -> before_view
same_start -> now_view
```

Why gains differ between tests:

```d2
direction: down

small_scope: {
  label: "Small-scope test (defaultPath=/crap)"
  tracked: "Tracked tree is already small"
  baseline: "Main is already cheap"
  branch: "Branch still helps, but less visibly"
  tracked -> baseline -> branch
}

large_scope: {
  label: "Large-scope test (defaultPath=/)"
  tracked: "Tracked tree is very large"
  baseline: "Main copies broad path set on miss"
  branch: "Branch copies changed paths only"
  result: "Bigger visible gain"
  tracked -> baseline -> branch -> result
}
```

### Story Beat 3: Sync scope key - why reuse is safe/correct

What to say:
1. We compute one stable `sync scope key` from sync settings.
2. We use that key to read/write "latest snapshot head for this scope".
3. Different settings get different keys, so they never mix.
4. This is separate from digest lookup:
5. Scope key drives parent selection when materializing.
6. Digest lookup drives direct immutable-ref reuse.

```d2
direction: down

inputs: {
  label: "Inputs used to build sync scope key"
  path: "source path"
  include: "include patterns"
  exclude: "exclude patterns"
  gitignore: "gitignore mode"
  rel: "relative path"
}

scope_key: "Stable sync scope key (hash of inputs)"
head_table: "In-memory table: scope key -> latest scope head"
entry: "scope head = {snapshot ref, checksum, depth, generation}"
lookup: "On next sync with same settings, read this head first"
isolation: "Different settings => different scope key => different table row"
digest_lookup: "Digest reuse path: checksum digest -> root index/contenthash (global search)"
parent_path: "Parent selection path (scope-key based)"

inputs.path -> scope_key
inputs.include -> scope_key
inputs.exclude -> scope_key
inputs.gitignore -> scope_key
inputs.rel -> scope_key
scope_key -> head_table -> entry -> lookup
scope_key -> isolation
scope_key -> parent_path
digest_lookup -> parent_path: "independent from scope key"
```

### Story Beat 4: Depth cap/rebase guardrails

```d2
direction: down

guardrails: {
  label: "Current guardrails (when materializing)"
  start: "Lookup miss: must build a new snapshot"
  load_head: "Load scope head (has previous ref + chain depth)"
  check_depth: "Depth < 128?"
  reuse_parent: "Yes: reuse previous snapshot as parent"
  rebase_empty: "No: rebase this sync on empty parent"
  apply_delta: "Apply deletes + copy changed paths (+ required parents)"
  commit: "Commit + finalize immutable snapshot"
  save_head: "Save new scope head with updated depth/generation"
  runtime_note: "Scope-head table is runtime-memory scoped (current engine process)"

  start -> load_head -> check_depth
  check_depth -> reuse_parent: "yes"
  check_depth -> rebase_empty: "no"
  reuse_parent -> apply_delta
  rebase_empty -> apply_delta
  apply_delta -> commit -> save_head -> runtime_note
}

invariant: "Invariant: returned outputs are immutable in both branches"
guardrails.commit -> invariant
```

### Story Beat 5: Destination (real tree-CAS)

What to say:
1. Current work is not full tree-CAS yet.
2. It intentionally prepares the migration path by proving incremental value and adding the core building blocks.

```d2
direction: down

future: {
  label: "Method 3 (target tree-CAS)"
  step1: "1) Receive host changes and detect changed files"
  step2: "2) For changed files: hash bytes and store blobs by digest"
  step3: "3) Update manifest (path -> blob digest + metadata)"
  step4: "4) Compute root manifest digest"
  step5: "5) Try root-digest lookup"
  hit: "Hit: return existing immutable output"
  miss: "Miss: materialize only needed paths from manifest plan"
  step6: "6) Commit/finalize immutable output"
  step7: "7) Save root-digest index"
  note: "Result: unchanged files keep same blob digest pointers (no byte recopy)"

  step1 -> step2 -> step3 -> step4 -> step5
  step5 -> hit: "reuse found"
  step5 -> miss: "reuse not found"
  miss -> step6 -> step7 -> note
}

bridge: "Current branch is bridge step: build less on small edits and reuse prior snapshots safely"
future.note -> bridge
```

## 2) What We Were Doing (Baseline behavior)

Core path in baseline:

1. `FileSyncer.Snapshot` -> `sync` -> `localFS.Sync`.
2. `localFS.Sync` creates a new output mutable ref.
3. Diff/apply updates the mirror and tracks path sets.
4. Checksum is computed.
5. Contenthash lookup attempts reuse.
6. On miss, copy into output + commit/finalize.

Why this can be expensive for large contexts:

1. Diff walk tracks many paths, including unchanged (`none`) paths.
2. Copy selection (`only`) can remain large.
3. A tiny change in a large context can still trigger large output materialization work.

## 3) What We Are Doing Now

No API or semantic rewrite; this is a scoped optimization in filesync materialization.

### 3.1 Scope identity is explicit

`FileSyncer.sync` computes a deterministic scope key from:

1. Client path.
2. Include patterns.
3. Exclude patterns.
4. GitIgnore mode.
5. Relative path.

References:

1. `engine/filesync/filesyncer.go:195-205`
2. `engine/filesync/cas/scope.go:13-63`

### 3.2 Runtime scope heads are shared inside FileSyncer

Scope head state is now owned by `FileSyncer` and injected into `localFS` shared state.

References:

1. `engine/filesync/filesyncer.go:29-35`
2. `engine/filesync/filesyncer.go:41-50`
3. `engine/filesync/filesyncer.go:52-79`
4. `engine/filesync/filesyncer.go:346-350`

### 3.3 Parent-based incremental materialization

In `localFS.Sync`:

1. Load scope head.
2. If depth is under cap, resolve previous immutable ref as parent.
3. Create new mutable ref with that parent.
4. Build explicit delta sets: `upsertSet`, `deleteSet`, `noneSet`.
5. For parent-based mode, copy set becomes expanded `upsertSet` ancestry, not full `only`.
6. Apply projected deletes before copy.

References:

1. Parent reuse decision: `engine/filesync/localfs.go:160-185`
2. Delta sets: `engine/filesync/localfs.go:232-235`, `558-560`
3. Copy set switch: `engine/filesync/localfs.go:888-891`
4. Delete projection/apply: `engine/filesync/localfs.go:892-907`, `1096-1155`

### 3.4 Reuse lookup order changed

Lookup order is now:

1. Root-digest index (`filesync.search_root_index`).
2. Contenthash search fallback (`filesync.search_contenthash`).
3. Materialize if both miss.

References:

1. Root index search/hit path: `engine/filesync/localfs.go:694-755`
2. Contenthash search/hit path: `engine/filesync/localfs.go:759-824`

## 4) Options Considered

We evaluated three directions.

## Option A: Hardlink-focused copy optimization

What it is:

1. Push harder on hardlink copy optimizations when safe.

Pros:

1. Small code surface.
2. Can reduce copy cost in eligible paths.

Cons:

1. Safety conditions are strict.
2. Does not by itself solve large unchanged selection/materialization structure.

## Option B: Parent-based delta materialization (chosen now)

What it is:

1. Reuse prior scope output as parent.
2. Materialize deltas from mirror using smaller copy set.

Pros:

1. Fastest practical POC.
2. Keeps current architecture and semantics.
3. Delivers measurable wins on warm large-context incremental runs.

Cons:

1. Still parent-chain based, so depth must be managed.

## Option C: Full tree-CAS snapshots (next-stage design)

What it is:

1. Blob digest store + manifest/tree digest snapshots as primary identity model.

Pros:

1. Better long-term scaling model.
2. Less coupling to parent-chain behavior.

Cons:

1. Larger implementation and validation effort.

## Why Option B first

1. Best speed-to-signal for a scoped POC.
2. Low migration risk.
3. Gives hard telemetry evidence before broader CAS investment.

## 5) Layer/Parent Depth Limit and Compaction Behavior

Cap:

1. `maxParentMaterializeChainDepth = 128`.
2. Parent reuse allowed only when `head.ChainDepth < cap`.

References:

1. `engine/filesync/localfs.go:42`
2. `engine/filesync/localfs.go:1092-1094`

What happens at cap:

1. Parent-based mode is disabled for that sync.
2. New output mutable ref is created with `nil` parent.
3. Materialization proceeds normally.
4. Scope head depth for the new lineage is reset by persistence logic.

References:

1. Cap decision path: `engine/filesync/localfs.go:165-179`
2. Depth progression/reset logic: `engine/filesync/localfs.go:647-653`

Practical interpretation:

1. We keep bounded chain growth.
2. We periodically rebase/squash behavior by construction.
3. This is a bounded parent-chain strategy, not yet full tree-CAS identity.

## 6) In-Depth Implementation Walkthrough

## 6.1 `engine/filesync/filesyncer.go`

What to read:

1. `FileSyncer` fields and constructor for `scopeHeads`.
2. `Snapshot` and `sync` for control flow.
3. `getRef` for mirror reuse and injection of `scopeHeads` into shared state.

Review checklist:

1. Scope key formation uses canonical inputs.
2. `scopeHeads` lifetime is tied to `FileSyncer` runtime.
3. Existing mirror ref lifecycle behavior remains intact.

## 6.2 `engine/filesync/localfs.go`

What to read:

1. `Sync` start and parent-ref selection.
2. Diff/apply and delta set collection.
3. Root index lookup and contenthash fallback.
4. Materialize path (`copyOnly`, delete projection, copy/commit/finalize).
5. Scope head persistence and chain depth updates.

Review checklist:

1. Parent mode only when safe and under cap.
2. `copyOnly` reduction is applied only in parent mode.
3. Delete application happens before copy in parent mode.
4. Immutability flow (commit/finalize) remains unchanged.

## 6.3 `engine/filesync/cas/*`

`scope.go`:

1. Canonicalization rules.
2. Path normalization and path-escape rejection.

`store_index.go`:

1. Root digest -> ref metadata index save/resolve.
2. Deterministic resolved candidate ordering.

`types.go`:

1. Shared CAS model primitives (`ScopeKey`, `Manifest`, `ScopeHead`, etc.).

`store_metadata.go` (available, partially staged for longer-term path):

1. Scope head metadata persistence and generation checks.
2. Manifest payload storage/load/validation.

## 6.4 Tests to anchor behavior

Primary integration tests:

1. `TestCrossSessionContextualDirChange` (small scope, low expected delta).
2. `TestCrossSessionContextualDirChangeMonorepo` (large host dir scope).
3. `TestCrossSessionContextualDirChangeMonorepoContextDirectory` (large module context `/`).

Reference:

1. `core/integration/cross_session_test.go:1014-1220`

## 7) How to Navigate the Files Quickly During Review

Suggested reading order:

1. `engine/filesync/filesyncer.go`
2. `engine/filesync/localfs.go`
3. `engine/filesync/cas/scope.go`
4. `engine/filesync/cas/store_index.go`
5. `core/integration/cross_session_test.go`

Use these commands:

```bash
rg -n "scopeKey|scopeHeads|Sync\(|search_root_index|copyOnly|maxParentMaterializeChainDepth" engine/filesync
rg -n "TestCrossSessionContextualDirChange" core/integration/cross_session_test.go
```

## 8) How to Explain Trace Differences Between Tests

For each run, separate these phases:

1. Mirror receive/apply cost: `filesync.diff_apply`.
2. Reuse lookup cost: `filesync.search_root_index`, `filesync.search_contenthash`.
3. Materialization cost: `filesync.copy_data + commit + finalize`.

Key fields:

1. `filesync.path.only` (full tracked set).
2. `filesync.path.copy_only` (actual copied set).
3. `filesync.materialize.parent_based`.
4. Temporary log line fields: `mode`, `copy_only`, `copy_ms`, `materialize_ms`.

Why tests differ:

1. Small scope (`/crap`) naturally has low baseline copy, so gains are small.
2. Large scope (`/`) has huge tracked set, so parent-based reduced copy set can produce visible wins.

## 9) Known Constraints and Current Boundaries

1. Scope-head sharing is runtime-memory scoped (current engine lifetime).
2. Full differential parity gate (`legacy` vs `cas`) is still part of remaining rollout work.
3. Warning-level perf logs are temporary instrumentation and should be removed after validation.

## 10) Single-Sentence Bottom Line

We kept filesync semantics and immutability intact, but changed the materialization strategy for warm incremental runs to be scope-aware and parent-delta-driven, with bounded chain depth and traceable performance evidence.
