# Review boundaries for the frozen streaming experiment

Read-only source review during the default-route A/B capture. This inventory is
not maintainer approval or a claim that the combined candidate is shipping-ready.
Both sources are parent503d / upstream main7c35. Heavy work remained sequential.

## Independent changes

1. Dagger snapshot cleanup: retain the completed parent for release if a later
   import fails (`engine/snapshots/pull.go`). Small correctness prerequisite.
2. Dagger reuse ownership: pin the reused snapshot/content ancestor closure to
   the current operation lease (`pull_reuse_lease.go`). Preserve normal GC and
   immutable result ownership; no new egraph key or persisted callback.
3. Dagger verified-download pipeline: overlap complete blob fetching with ordered
   import (`pull_pipeline.go`). This can be evaluated without private streaming
   or modified containerd; activation should stay independently reviewable.
4. Containerd progress-reader shutdown synchronization (`core/diff/apply/apply.go`).
5. Containerd input-first asynchronous decoder teardown, retaining the last
   initialized processor on setup failure. Deterministic before/after race test
   evidence is retained in this owner.
6. Containerd bounded ordered hash worker. This is a performance change, distinct
   from the two lifecycle changes; the combined A/B cannot isolate its benefit.
7. Dagger verified private final-layer streaming (`streamed_fetch.go` plus applier
   factory/publication fences). This is the larger dependent optimization.

The optional `content.NewReader` / `Reader()` contract already exists in stock
containerd; this experiment does not introduce that API. The implementation
changes still need upstream containerd review/release and a normal Dagger
dependency update. The local Go replacement is only experimental. Publish inert
patches and evidence on the fork until those delivery requirements are met.

## Compatibility and performance follow-ups

- `core/container_image.go` currently enables both pipeline and private streaming
  unconditionally in this candidate. It is not a shipping opt-in.
- Current final-layer eligibility checks callbacks/factory and unique digest, not
  processor/media capability. Unsupported random reads, reset or truncate fail
  safely but do not retry eagerly in the same command. Universal activation needs
  explicit supported-path gating or complete teardown and fresh-snapshot fallback.
- The Windows-layer wrapper bypasses the patched containerd applier. Its current
  deferred decoder/input close order and cancellation mutex are unvalidated with
  private streaming. This is a source-identified risk, not a reproduced bug, and
  is outside the measured Linux/direct-compression Rust path.
- Waiting for the final layer's parent before starting its download can sacrifice
  transfer concurrency. Retain full-flow losses; do not report only unpack gain.
- Repeated reused-layer ancestor closure walks may repeat metadata work quadratically.
  Future operation-local deduplication must preserve existence/lease/GC validation.
- Borrowed input reads are not universally interruptible, and progress callbacks
  must not reenter the reader. The tested cleanup is not an arbitrary multistage
  external-processor lifecycle guarantee.
- A historical test comment says it has not been run; leave frozen measured source
  unchanged, then correct that comment in any separately prepared publication.

The publication fence remains mandatory: complete compressed-content verification,
calculated diffID verification and source labeling succeed before snapshot commit.
No Cargo command consumes a partial rootfs. Timed results must still pass complete
wcprof, actual execution, affected-crate, restart and full image-byte audits.
