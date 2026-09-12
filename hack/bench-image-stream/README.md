# Experiment: overlap verified image download and extraction

This branch preserves a measured engine experiment, not a shipping default,
new snapshotter, or complete portable Rust demo. It is stacked on the independent
containerd progress-reader fix and based on upstream main
6bf59d50654ce9244ebeee1cc090b7dce3fe3083 (reverified 2026-09-12). Ordinary Dagger
builds are unchanged: the proposed source changes are inert patch artifacts.
No PR, public engine image, or maintainer approval is implied.

New same-Zstd composition experiment: [ZSTD_RESULTS.md](ZSTD_RESULTS.md) and
[ZSTD_VALIDATION.md](ZSTD_VALIDATION.md). It saves 0.934 s in the shared cold image
path, but only 0.333 s at the paired full-CLI median; edit paths regress. It adds
focused tests/evidence, not a production change or a promoted default.

The corrected candidate saved a paired median **2.276721 seconds** for a
profiled first check in three fresh-engine AB/BA/AB pairs against the previous
bounded-hash candidate. All three cold pairs favored it, but the largest gain
includes a retained control outlier. Median provisioning-plus-check overhead
versus native remains **7.549737 seconds**. Warm overhead did not improve.
This is useful cold-path progress, not the Rust-module performance goal met.

See [RESULTS.md](RESULTS.md), [corrected-summary.json](corrected-summary.json),
and [initial-summary.json](initial-summary.json). The initial candidate later
failed a larger race fixture; its favorable timings are not promoted and its
losing pair is retained. Do not pool the two different candidates.

## Mechanism and Dagger boundaries

[engine.patch](engine.patch) overlaps verified preceding-layer work and streams
one eligible unique final layer through an owned bounded pipe into a private
snapshot. Full compressed bytes are downloaded and verified; extraction computes
the uncompressed digest; committed content, source labeling and verification
must finish before an immutable result can be published. Existing content-store,
snapshot, lease, cache identity and result-publication machinery remains in use.
No Cargo execution consumes an incompletely verified filesystem. Fallbacks and
ownership/release/GC/error paths are tested, not bypassed for the benchmark.

The private reader closes its owned pipe and fences active reads before returning
from Close. This is deliberately narrower than joining arbitrary borrowed
containerd readers. The parent branch documents that separate progress fix.
[containerd.patch](containerd.patch) combines that fix with the prior bounded
hash worker. Apply it to **fresh stock v2.2.5**, not on top of either old patch.
Shipping that dependency work requires upstream review/release and a normal
Dagger dependency update; no local replacement is proposed as shipping policy.

The final download starts after the parent import. Lost download concurrency can
erase the gain; cold samples, including outliers, must account for it. The patch
also contains import/pipeline reuse and lease prerequisites, so it is an
experimental bundle needing review/splitting, not a claim of a tiny ready PR.

## Reproduce source and supported correctness checks

Use disposable Dagger and containerd checkouts, never the shared Go module cache.
`EVIDENCE` denotes this directory; `CONTAINERD_CHECKOUT` is fresh v2.2.5 source.

```sh
git -C "$CONTAINERD_CHECKOUT" apply --check "$EVIDENCE/containerd.patch"
git -C "$CONTAINERD_CHECKOUT" apply "$EVIDENCE/containerd.patch"
cp "$EVIDENCE/../bench-image-reader-lifecycle/fixtures/progress_reader_test.go.txt" \
  "$CONTAINERD_CHECKOUT/core/diff/apply/progress_reader_test.go"
git apply --check "$EVIDENCE/engine.patch"
git apply "$EVIDENCE/engine.patch"
cp "$EVIDENCE/fixtures/pipelined_apply_test.go.txt" engine/snapshots/pipelined_apply_test.go
cp "$EVIDENCE/fixtures/pipelined_apply_compressed_test.go.txt" engine/snapshots/pipelined_apply_compressed_test.go
```

The expected combined apply.go SHA256 is
820da9e1efc0ef78b29ac1a55590f426ab5a76188e57004c954e2ec413e8f91e.
The engine patch applies cleanly to the base main revision plus the inert parent
evidence branch. To run the experiment, stage the dependency source under the
normal engine-dev source allowlist (such as internal/) and use a temporary local
go.mod replace only in that disposable checkout. The measured build controller
pins the full local dependency tree; that temporary replacement is not included
in engine.patch.

```sh
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call engine-dev test \
  --pkg=./engine/snapshots \
  --run='^(TestPipelinedApply|TestImportImage(Pipeline|Reuse|LayerReuse)|TestStreamedImport)' \
  --race=true --count=3 --parallel=1 --timeout=90s --test-verbose=true
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call engine-dev test \
  --pkg=./core/integration \
  --run='^TestEngine$/^TestVerifiedStream(LargePrivateSnapshotRace|RealPrivateSnapshotRace)$' \
  --parallel=1 --timeout=5m --count=1 --test-verbose=true
```

The latter tests invoke race-enabled real mounted-snapshot suites three times
each, including the default external decoder and a 10 MiB compressed input that
crosses the hash-worker threshold. Final supported runs and complete CLI build
passed; this is not exhaustive concurrency, portability or production validation.

The host-specific full-CLI controllers and raw evidence are recorded in RESULTS.
They depend on the separately retained experimental module/CLI stack. This small
branch alone does not install that stack or reproduce onboarding on a clean
machine. Maintained private wcprof code and raw HTTP/OTel data are not published.
