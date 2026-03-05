# Scoped Filesync-CAS Plan (Dev Engine, Linux Scope)

## 0) How to read this document

This plan is intentionally split in two layers:

1. **Simple spec**: what we are building and why, in operational terms.
2. **Advanced spec**: exact data model, algorithm, invariants, and implementation details.

Then we keep the full **commit-by-commit execution plan** with mandatory tests and checkpoints.

---

## 1) Simple Spec (for non-experts)

### Problem today

When a host directory is synced, the engine can still do a lot of output materialization work after a tiny edit.

Typical case:

1. You modify one file.
2. Sync still spends a lot of time rebuilding/copying output filesystem state.

### What we are changing

We keep the current mutable mirror sync logic, but we change how final snapshot identity and reuse work:

1. File contents are stored once by digest (`BlobStore`).
2. Directory state is represented by a deterministic manifest/tree digest (`rootDigest`).
3. Snapshot reuse is keyed by `rootDigest`.

### Before vs after

#### Before (current path)

1. `FileSyncer.Snapshot` syncs host changes into mutable mirror.
2. `localFS.Sync` creates a new output **mutable** ref from empty parent (`cacheManager.New(..., nil, ...)`), then commits it to an **immutable** ref at the end.
3. Diff includes unchanged entries (`ChangeKindNone`) in the tracked copy set.
4. Copy runs from mirror to empty destination with `fscopy.Copy + Only`.
5. Because destination starts empty, many unchanged files still get materialized.
6. If resulting digest differs (for example one file changed), that materialization work repeats.

#### After (target path)

1. Keep mirror diff/apply logic unchanged.
2. Build delta sets from sync: `upsert`, `delete`, `none`.
3. For changed regular files, compute blob digest and store bytes once by digest.
4. Update manifest entries and recompute deterministic `rootDigest`.
5. Lookup `rootDigest -> immutableRef`.
6. If hit: return existing ref, no rematerialization.
7. If miss: materialize only changed/deleted paths from manifest delta.
8. Persist scope head for next sync.

### Why this helps

1. Small edits mostly do small work.
2. No-change reruns collapse to digest-hit reuse.
3. Unchanged bytes are referenced by digest, not recopied.
4. Output remains immutable and cache-safe.

### Linux scope (explicit)

This delivery targets:

1. Linux engine runtime.
2. Linux caller behavior.

Windows/macOS caller parity is deferred.

### Quick glossary

1. **Mutable mirror**: writable per-client filesystem view during sync.
2. **Blob**: file bytes stored by content digest.
3. **Manifest**: canonical path/metadata map pointing to blobs.
4. **Root digest**: digest of the manifest/tree; snapshot content identity.
5. **Scope head**: latest root digest for one sync scope.

---

## 2) Advanced Spec (exact behavior)

## 2.1 Goal

Implement a scoped filesync-local CAS model for host imports that:

1. Keeps current mutable mirror behavior for diff/apply.
2. Switches snapshot identity to root manifest digest.
3. Reduces rematerialization for small changes.
4. Preserves host import semantics.

## 2.2 Scope

1. Runtime target: Linux engine + Linux caller.
2. Applies to all `FileSyncer.Snapshot` users (`host.directory`, `host.file` via directory path).
3. No runtime feature flags for this effort.
4. Safety is enforced by tests, invariants, and checkpoints.

## 2.3 Out of scope

1. Full platform-wide CAS rewrite.
2. Windows/macOS caller behavior parity.
3. Public GraphQL/API changes.

## 2.4 Architecture summary

1. Keep mutable mirror (`localFS`) as source of truth for incoming host diffs.
2. Add filesync-scoped CAS layer:
   - `BlobStore`: `digest -> bytes`
   - `Entry`: path metadata + blob/link info
   - `Manifest`: canonical sorted entries + root digest
   - `ScopeHead`: `scopeKey -> root digest + materialized ref + generation + chain depth`
3. Reuse existing cache/snapshot/content primitives for materialization and metadata.

## 2.5 Data model

```go
type ScopeKey string

type EntryKind uint8
const (
  EntryFile EntryKind = iota + 1
  EntryDir
  EntrySymlink
  EntryHardlink
)

type Entry struct {
  Path       string
  Kind       EntryKind
  Mode       uint32
  UID        uint32
  GID        uint32
  Size       int64
  LinkTarget string
  BlobDigest digest.Digest
  XAttrs     map[string][]byte
}

type Manifest struct {
  Version    uint32
  Scope      ScopeKey
  Entries    map[string]Entry
  RootDigest digest.Digest
}

type ScopeHead struct {
  Scope         ScopeKey
  RootDigest    digest.Digest
  MaterialRefID string
  Generation    uint64
  ChainDepth    uint32
}
```

## 2.6 Hashing and identity rules

1. Blob digest: `sha256(file bytes)`.
2. Tree digest: deterministic hash over canonical sorted entries.
3. Keep existing `xxh3` fast local hashing where already used in filesync internals.
4. Persisted CAS identity uses `sha256` in phase 1.
5. mtime is excluded from persisted identity.

## 2.7 Execution algorithm

1. Run current mirror sync/apply as-is.
2. Derive `upsertSet`, `deleteSet`, `noneSet` from sync results.
3. Load previous manifest for `scopeKey`.
4. Apply deletes to manifest.
5. For each regular file in `upsertSet`:
   - compute digest
   - write blob if missing
   - update entry metadata + blob digest
6. For non-regular in `upsertSet`:
   - update metadata + link target as relevant
7. Recompute root digest.
8. Lookup `rootDigest -> immutableRef` index.
9. If hit, return ref.
10. If miss, materialize immutable ref from manifest delta.
11. Persist root index and scope head.

## 2.8 Integration points with current engine

1. Keep host->engine transfer and mirror mutation logic unchanged.
2. Keep include/exclude/gitignore/relativePath semantics.
3. Insert CAS layer between "mirror updated" and "final immutable output".
4. Reuse existing engine primitives for:
   - immutable ref creation/commit/finalize
   - metadata/index persistence
   - content-store blob IO
5. Keep legacy path as test oracle until parity is proven.

## 2.9 Invariants (must always hold)

1. Old immutable refs remain immutable.
2. Same effective filesystem view yields same root digest.
3. Deletes are exact and deterministic.
4. include/exclude/gitignore/relativePath behavior matches legacy.
5. Same-scope concurrent syncs are serialized and deterministic.
6. Different scopes do not interfere.
7. Path traversal outside root is rejected.

## 2.10 Mandatory stopgaps

1. Keep legacy path callable as internal oracle during migration.
2. Add differential tests (`legacy` vs `cas`) and block progression on mismatch.
3. Bound chain depth and force squash/rebase when threshold is reached.
4. Add manifest size guard and deterministic error path.
5. Add strict generation checks on scope-head writes.

---

## 3) Per-Commit Contract

Each sub-subtask is one commit, and each commit must include:

1. Code for one concern only.
2. Tests for that concern.
3. Doc delta in this file (append one line under Progress Log).
4. Successful local verification commands.

Commit message format:

1. Subject: `filesync-cas: <what changed>`
2. Body sections:
   - Why
   - What
   - Tests
   - Docs

---

## 3.1) Review Cadence (one commit at a time)

Every commit is reviewed before the next commit starts.

For each commit:

1. Implement only that commit scope.
2. Run only that commit's verification commands.
3. Capture evidence:
   - `git show --stat --name-only HEAD`
   - key test output lines
   - key trace evidence for runtime-impacting commits
4. Reviewer checks and explicitly approves.
5. Then start the next commit.

If a commit scope grows beyond one concern:

1. Stop.
2. Split into two commits.
3. Re-run review loop.

## 3.2) Per-Commit Review Template

Use this exact template in review notes:

1. Commit:
2. Why:
3. Files touched:
4. Behavioral change:
5. Risks:
6. Tests run:
7. Trace/telemetry evidence:
8. Reviewer verdict:

---

## 4) Commit Plan

### Commit 00: Trace-first observability + monorepo repro harness

1. Add filesync phase telemetry on trace spans/events:
   - `diff_apply_ms`
   - `checksum_ms`
   - `search_ms`
   - `copy_ms`
   - `commit_ms`
   - `finalize_ms`
   - `materialize_ms`
2. Ensure data is emitted as span attributes/events (not only plain logs).
3. Add large-context cross-session integration repro tests:
   - monorepo host.directory path
   - monorepo module `defaultPath="/"` (`_contextDirectory` path)
4. Verification:
   - `go test ./engine/filesync/...`
   - `go test ./core/integration -run '^TestDoesNotExist$' -count=1`
   - targeted integration run with trace evidence capture
5. Reviewer focus:
   - confirms phase breakdown is visible in traces
   - confirms monorepo repro is stable and deterministic

### Commit 01: Plan + baseline harness doc

1. Add this plan file and checklist.
2. No runtime behavior change.
3. Verification:
   - `go test ./engine/filesync/...`

### Commit 02: Characterization tests for current behavior

1. Add/expand tests freezing current semantics before CAS changes.
2. Focus:
   - include/exclude/gitignore behavior
   - deletion behavior
   - change cache behavior
3. Verification:
   - `go test ./engine/filesync/...`

### Commit 03: CAS core types and scope-key canonicalization

1. Create `engine/filesync/cas/types.go` and `scope.go`.
2. Define `ScopeKey`, `Entry`, `Manifest`, `ScopeHead`.
3. Add unit tests:
   - scope key determinism
   - path normalization and escape rejection
4. Verification:
   - `go test ./engine/filesync/cas -run 'TestScope|TestPath'`

### Commit 04: Manifest canonical serialization

1. Add `manifest.go` canonical marshal/unmarshal with stable order.
2. Add tests:
   - stable byte representation independent of insertion order
   - roundtrip consistency
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestManifestSerialization|TestManifestRoundtrip'`

### Commit 05: Merkle digest for entries/tree

1. Add `hash.go` implementing deterministic entry/root digest.
2. Add tests:
   - deterministic digest
   - metadata-only change updates root
   - rename reuses blob digest but changes tree root
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestManifestDigest|TestRename|TestMetadata'`

### Commit 06: Scope head + manifest metadata stores

1. Add metadata-backed stores in `store_metadata.go`.
2. Add tests:
   - save/load head
   - generation increment checks
   - corrupted payload handling
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestHeadStore|TestManifestStore|TestCorrupt'`

### Commit 07: Root digest index store

1. Add `store_index.go` for root digest -> immutable ref lookup.
2. Add tests:
   - index write/read
   - idempotent reinsert
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestRootIndex'`

### Commit 08: Blob store adapter

1. Add `store_blob.go` backed by existing content store.
2. Add tests:
   - has/put/open roundtrip
   - digest mismatch handling
   - idempotent writes
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestBlobStore'`

### Commit 09: localFS delta extraction refactor (no behavior change)

1. Refactor local sync internals to output explicit delta sets:
   - `upsertSet`
   - `deleteSet`
   - `noneSet`
2. Add tests:
   - categorization correctness by change kind
3. Verification:
   - `go test ./engine/filesync/...`

### Commit 10: Apply delta to manifest

1. Add `apply_delta.go`.
2. Update/insert/delete entries from sync delta.
3. Tests:
   - add/modify/delete/symlink/hardlink matrix
4. Verification:
   - `go test ./engine/filesync/cas -run 'TestApplyDelta'`

### Commit 11: Materialization planner

1. Add `materialize_plan.go` generating minimal ops from old manifest to new manifest.
2. Tests:
   - minimal plan for 1-file modify
   - delete-heavy plan
3. Verification:
   - `go test ./engine/filesync/cas -run 'TestMaterializePlan'`

### Commit 12: Materialization executor

1. Add `materialize_exec.go` to realize plan into immutable ref.
2. Include mount lifecycle and cleanup guarantees.
3. Tests:
   - expected tree output
   - cleanup on mid-exec failures
4. Verification:
   - `go test ./engine/filesync/cas -run 'TestMaterializeExec'`

### Commit 13: Wire CAS runtime path in filesyncer/localfs

1. Integrate CAS flow into `FileSyncer.Snapshot`.
2. Keep legacy path callable in tests as oracle.
3. Tests:
   - differential parity tests at unit level
4. Verification:
   - `go test ./engine/filesync -run 'TestLegacyVsCASParity' -count=1`

### Commit 14: Chain depth cap + squash/rebase

1. Add bounded depth policy and squash trigger.
2. Tests:
   - threshold hit forces squash
   - post-squash correctness
3. Verification:
   - `go test ./engine/filesync -run 'TestChainDepth|TestSquash'`

### Commit 15: Integration tests (host import parity + immutability)

1. Add/extend integration tests in `core/integration`.
2. Required scenarios:
   - cross-session contextual dir change
   - cross-session delete
   - old snapshot immutability after host change
3. Verification:
   - `dagger --progress=plain call engine-dev test --pkg ./core/integration --run '^TestModule/TestCrossSessionContextualDir(Change|Delete|CacheHit)$' --test-verbose`

### Commit 16: CAS telemetry instrumentation

1. Add counters/histograms:
   - blob hit/miss bytes
   - root hit/miss
   - manifest size
   - chain depth
   - materialization duration
2. Verification:
   - `go test ./engine/filesync/...`
   - one integration rerun with plain progress to inspect spans

### Commit 17: Final cleanup + docs finalization

1. Remove transitional code only after all parity gates pass.
2. Finalize docs with measured before/after data.
3. Verification:
   - `go test ./engine/filesync/...`
   - `go test ./core/integration/... -run '^TestModule/TestCrossSessionContextualDir.*$'`

---

## 5) Checkpoints You Can Run

### Baseline check

1. `go test ./engine/filesync/...`
2. `dagger --progress=plain call engine-dev test --pkg ./core/integration --run '^TestModule/TestCrossSessionContextualDirChange$' --test-verbose`

### Per-commit check

1. `git show --stat --name-only HEAD`
2. Run the commit's exact test command(s).
3. Confirm no unrelated files changed.

### Differential gate check

1. `go test ./engine/filesync -run 'TestLegacyVsCASParity' -count=1`
2. Must be green before advancing to next runtime-impacting commit.

### End-to-end small-change check

1. Run targeted integration test once.
2. Edit one relevant file in repo.
3. Rerun same test.
4. Confirm reduced filesync materialization work and no result drift.

### Trace breakdown check

1. `dagger --progress=plain call engine-dev test --pkg ./core/integration --run '^TestModule/TestCrossSessionContextualDirChangeMonorepo$' --test-verbose`
2. Extract span evidence showing:
   - mirror receive/apply (`diff_apply_ms`)
   - layering (`copy_ms + commit_ms + finalize_ms`, and `materialize_ms`)
3. Repeat with:
   - `^TestModule/TestCrossSessionContextualDirChangeMonorepoContextDirectory$`
4. Confirm `_contextDirectory` path shows same bottleneck signature before CAS rollout.

---

## 6) Go/No-Go Rules

Stop and fix before proceeding if any of these happen:

1. Differential parity mismatch.
2. Immutability regression.
3. include/exclude/gitignore semantics drift.
4. Unbounded chain depth behavior.
5. Root digest index maps to wrong content.

---

## 7) Acceptance Criteria

1. All commit-level tests and integration checkpoints pass.
2. Differential parity suite is green.
3. One-file-change rerun shows reduced rematerialization/copy work.
4. No behavior regressions for Linux engine + Linux caller host imports.

---

## 8) Progress Log

1. Baseline observability + monorepo repro landed:
   - `37ad7073b` (`filesync: track explicit delta sets in local sync telemetry`)
   - `29896076f` (`filesync-cas: add temporary phase tracing and monorepo cross-session tests`)
2. CAS primitives landed:
   - `74031c652` scope-path normalization reuse
   - `0e2f29364` manifest canonical serialization
   - `b209de8dc` deterministic entry/root digesting
   - `859ef8bb7` scope-head/manifest metadata stores
   - `565f31f83` root digest index store
   - `472c99045` blob store adapter
   - `84ea06fae` manifest delta application
   - `7a2493db4` materialization planner
   - `e0a4b1310` materialization executor abstraction
3. Runtime wiring landed:
   - `4d0b90590` scope key wiring in filesync path
   - `e3c968807` parent-delta materialization path
   - `179a1c149` parent-chain depth cap
   - `2f7fb9102` root digest index lookup before content-hash search
4. Test hardening landed:
   - `f59e96579` initialize real git repo in monorepo contextual-dir test to avoid malformed `.git` false failures
5. Runtime scope-head + perf visibility landed on branch:
   - global runtime scope-head store shared across FileSyncer instances
   - strict generation checks exercised in localFS helper tests
   - explicit warning-level filesync perf lines for temporary measurement (`mode`, `parent_based`, `copy_only`, `copy_ms`, `materialize_ms`)
6. Latest measured evidence (current branch):
   - one-file-change monorepo incremental path reached `parent_based=true`, `copy_only=9`, `copy_ms=2-3`, `materialize_ms≈69-85`
   - trace examples: `ca88518b6e7442309ef5ba9c14c8f5fc`, `bc5edfa405c2db77aa0aa85ba6ab9c90`
7. Remaining major work from plan:
   - legacy-vs-CAS differential parity harness
   - chain squash/rebase policy finalization (beyond depth cap)
   - finalize telemetry surface and remove temporary warning-level perf logs (keep span attributes/events as durable surface)
