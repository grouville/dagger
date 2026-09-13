# Cold image content-commit diagnostic

Status: **confirmed diagnostic, not a performance fix**. This branch changes no
active engine or Rust-module code. It stores the diagnostic containerd patch and
all measured flow rows so the finding is visible without pretending that a new
branch means a shipping speedup. No PR or public image publication accompanies it.

Stack parent: `perf/rust-24-module-url-lock`, commit
`5b8b036f8d7ae37b653078e81ca9b4edcf586be3`. Upstream main was reverified as
`7c35e6274737acff0f6bd76614abb5e04efa7d12` before publication on 2026-09-13.

## What we learned

Standard OCI zstd compression is not a consistent whole-command win in these
small cohorts. A fresh current-stack gzip/zstd comparison first located a
1147.793 ms interval after all bytes of a 24 MB layer arrived, before its content
commit finished. The complete trace could not distinguish synchronization from
metadata contention. We instrumented that boundary, preserved every existing
durability operation, and repeated the full workflow on a separate engine.

The new spans reproduced a larger tail and located it inside
`namespacedWriter.Sync -> local.writer.Sync -> os.File.Sync`, **before** the
metadata transaction:

| Observed phase | Slow zstd run (index 2) | Last zstd run (index 5) |
| --- | ---: | ---: |
| Standalone first CLI, including engine provisioning | 23.315617 s | 11.935840 s |
| Rust delivery/import envelope | 14.048242 s | 3.393864 s |
| Final 270.9 MB layer pre-sync | 8.765174 s | 0.145200 s |
| Parent 24.0 MB layer pre-sync | 1.441782 s | 0.013448 s |
| Connect | 1.541265 s | 0.954217 s |
| Source sync plus Cargo process | 5.863713 s | 6.055029 s |

These rows overlap; do not sum them. Content-lock acquisition for these layers
was under 0.01 ms. Their metadata transactions took approximately 1–3 ms. The
second file sync inside local commit was also tiny. This is not evidence of
egraph contention, stale Cargo fingerprints, or repeated crate compilation.

The filesystem/device reason for the slow sync is **not yet established**. The
diagnostic engine stores its state in a normal Docker local volume on the host's
ext4 filesystem. The trace does not separate pending file data, journal activity,
device contention, or other writeback behavior. No host settings were changed.

wcprof ranks preSync first in the slow run, with a modeled save-at-zero of 8.82s.
That is a what-if estimate, **not an achieved or promised speedup**. Removing
sync, weakening verification, or moving the wait into another phase is not a fix.

## Complete flow results, including losses

`flow-results.csv` contains 144 flow observations across two six-run cohorts.
Each cohort has only **three independent AB/BA/AB pairs**, not 72 independent
trials. A is gzip; B is zstd. Within each arm, exact/application/workspace-library
flows each have three observations; cold, external upgrade and follow-up each
have one. No run or outlier was discarded.

| Cohort | Gzip first CLI median | Zstd first CLI median | Paired CLI saving median [min, max] | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| codec-current, no new commit instrumentation | 13.188093 s | 11.869160 s | +0.290992 [-1.298187, +2.536901] s | 2/3 |
| commit-instrumented, same instrumentation on both sides | 12.487970 s | 11.935840 s | +0.552130 [-10.913156, +1.165307] s | 2/3 |

These are separate cohorts, not an instrumentation A/B test; differences between
their medians are not an instrumentation speedup/regression measurement.

Current diagnostic zstd flows, milliseconds:

| Flow | Native median | Dagger median | Median paired native overhead |
| --- | ---: | ---: | ---: |
| First check, engine provisioning included | 6728.352 | 11935.840 | +5206.287 |
| Exact unchanged | 119.303 | 516.657 | +395.119 |
| Application edit | 297.981 | 895.793 | +590.387 |
| Workspace-library edit | 464.335 | 1063.358 | +581.636 |
| Actual bstr 1.12.0 -> 1.13.0 upgrade | 1638.672 | 2221.424 | +567.746 |
| Exact after upgrade | 117.872 | 497.948 | +380.076 |

Paired medians are computed from differences, not by subtracting marginal
medians; columns therefore need not subtract exactly. Every flow median is still
slower than native. The drop-in Rust performance goal remains unmet.
For repeated warm flows, first take the median within each run, then the median
of the three independent run summaries; do not pool the nine repetitions.

The last zstd run's native comparator took 11.611s while Cargo reported 5.84s of
work. The slow zstd run's native comparator took 6.728s while Cargo reported
5.89s. Native logs lack the timestamps to split rustup bootstrap from lifecycle
delay. Thus the last run's measured +325ms Dagger overhead does **not** establish
generally achieving that overhead. The sample is retained, not excluded.

## Correctness and measurement scope

Each cohort passed:

- Six complete fresh-engine flows and ownership-checked cleanup. Ordinary image
  driver creates its engine and state volume inside the first CLI timer.
- 36 complete wcprof captures, zero rejected captures, no open/dropped events,
  structural gates passed, declared/received engine span counts equal. Replay
  drift -0.0% to -0.1%. Instrumented cold captures each have 319/319 engine spans.
- 18 cache analyses, 36 crate-rebuild audits, 54 ordinary timed execution audits.
  Exact and restart hits execute no Cargo/image work; app edits rebuild ripgrep;
  library edits rebuild the affected three-crate chain. Actual external bstr
  versions/rebuild sets and retained memchr are checked separately.
- Deliberate compilation failures, repairs, old-source revisits and restart
  reuse have their expected outcomes. Only expected-success commands must exit0.
- Complete compressed digest/size and decoded tar digest/size verification.
  Gzip 316873658 bytes versus zstd 294925737 bytes; both decode to exactly the
  same 77895680-byte and 837738496-byte tar streams, with identical image config.
- Registry, disposable engines/native containers and their owned volumes removed;
  existing host container inventory restored; retained build engines unchanged.

The new diagnostic also passed seven targeted existing top-level content-store
test groups under the race detector, with no skipped cases: metadata TestContent,
TestContentLeased, TestIngestLeased; local TestContent, TestContentWriter,
TestWriterTruncateRecoversFromIncompleteWrite, TestWriteReadEmptyFileTimestamp.
The source-built dev engine and an explicitly targeted smoke query passed.

Scope limits: prepopulated owned local registry, not public registry/CDN delivery
or complete installation. Docker, CLI, engine/native images, module source and
registry blobs already available. No source/target/crate/image prewarming in the
fresh engine stores. Host page/CDN caches were not purged. Native is `docker exec`
with a matching preinstalled compiler, not bare-host Cargo. Root toolchain setup
is inside the first command on each side. Dagger's pinned rsync installation also
remains inside its first check. Cold and upgrade commands use `--profile`; normal
warm commands do not, but still export local OTLP. Post-timer diagnostics are
outside timings. No listener/watch/manual resident worker. No artifact export,
fmt/clippy/test-command/macOS/remote performance validation is claimed here.

## Reproduction and implementation boundaries

The workload is ripgrep `3fce3b5bb0236da2df6d99672afb8a719642eca7`, configured
Rust1.97.1 minimal + rustfmt, `cargo check --workspace --locked`. The ordinary
Dagger command is `dagger --profile check rust:check` for cold/upgrade, and
`dagger check rust:check` for warm timings. The module runs
`rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked` with
locked mutable source/target caches and ordinary registry/git caches.

The published workload fixtures are at
[b5070c47, hack/bench-rust-loop](https://github.com/grouville/dagger/tree/b5070c47a3458a535294d13a212f2cd2d221c757/hack/bench-rust-loop).
The capture adapter changes provisioning to ordinary CLI-managed fresh engines:
`DAGGER_ENGINE=image+docker://<local-engine-tag>?container=<unique-name>&volume=<unique-name>&cleanup=false`.
Every arm has fresh XDG configuration/cache/data/state and a fresh native
container/workspace. Engine JSON contains only the exact owned registry's HTTP
setting. Existing engines are preserved; only validated owned targets are cleaned.

`instrument-containerd.patch` is a **diagnostic patch artifact**, not code wired
into this branch. It applies to the two containerd v2.2.5 source files used by
the retained runtime. Its normal containerd tracing provider inherits the Dagger
session provider, so wcprof counts the new spans automatically. It does not add
a Dagger dependency to containerd. Both sync calls, directory sync, error returns,
digest validation, lease transitions, locks and publication order remain intact.

For the recorded source layout, apply only in a separate experimental checkout:

```sh
git apply --check --directory=internal/bench-image-stream/containerd \
  /path/to/instrument-containerd.patch
git apply --directory=internal/bench-image-stream/containerd \
  /path/to/instrument-containerd.patch
go test -race -count=1 -p=2 -parallel=1 -timeout=5m \
  -run='^Test(Content|ContentLeased|IngestLeased)$' \
  github.com/containerd/containerd/v2/core/metadata
go test -race -count=1 -p=2 -parallel=1 -timeout=5m \
  -run='^Test(Content|ContentWriter|WriterTruncateRecoversFromIncompleteWrite|WriteReadEmptyFileTimestamp)$' \
  github.com/containerd/containerd/v2/plugins/content/local
```

That layout uses a local containerd replacement already present in the retained
streaming prototype. A stock checkout does not contain it. Rebuild through the
normal Dagger dev workflow, verify the new engine identity, capture raw OTLP with
`hack/otlpdump` and `--profile`, and require maintained wcprof completeness gates
before interpreting phases. In the spans, subtract transaction callback entry/
exit from transaction start/end to separate acquisition/setup from completion/
callbacks; do not label these intervals as pure Bolt lock/fsync. The final
streamed layer's final-write-to-commit-start gap can include pipe backpressure.

This branch is **not yet a turnkey public end-to-end reproduction** of the full
experimental runtime. Frozen owner-specific controllers, OCI archives and raw
telemetry remain local; private analyzer binaries/raw telemetry are not published.
The CSV and patch preserve the finding and review boundary without implying that
checking out this docs branch activates the measured engine stack.

## Provenance

Both runtimes inherit stream/containerd and Unix-readiness prototypes plus
perf23/perf24; neither is clean main versus the entire published stack.
Source HEAD `503d3410ef3df63fa6bc7a55c5c2453c4951c2c2`; full non-HEAD source
hashes were verified before/after capture. Only the two instrumented files differ.

- CLI SHA256: 6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad
- Prior engine image: sha256:915748ca80a3b9efaf1e99bb2e47c45ef637784772908116a869a2d41e56348f
- Instrumented engine image: sha256:562e6967b70539c267c395338bdf57acaa0f1dd8d8fad660f7888606aaf2ae4e
- Instrumented build receipt SHA256: 86284135ca90b89e4a405f1ffafebb63c67d38002225e73c92566364b58cd2b5
- Original cohort analysis SHA256: 1e9d11f43e4a2ff78375699f6943a7bb914d1f7790fd90e0e704e7b2776ed51f
- Instrumented cohort analysis SHA256: 83387b2603e2a3807b5287fc755e95fd1e476d9d753a9c2a139c2e6287a1cdf1
- Instrumented ordinary audit SHA256: 1735cb80d9a8b9931e9d68eb5914c3813cdc3e6ae6821e4f284983d06e888809
- Instrumented commit summary SHA256: 7974cf75ad9e252efec1b5bc91492a59bad3ad25f4ffdfc8f640287e3c5c34b5
- Instrumented raw OTLP SHA256 (43269445 bytes, retained privately): edfc3daaf5bea47aca26c82ffaf87e95cfcca8f00e4fc8bb8552644edd4e12ea

## Next work

Measure filesystem/writeback behavior at the confirmed sync boundary before
choosing a fix. A writeback-ahead experiment must retain final durability and
measure whole transfer/apply/commit latency, not merely move time out of preSync.

Separately, test ordinary prepared/flattened toolchain OCI packaging: bundle the
exact rsync/components, retain project-config handling, keep the complete
toolchain in the streamed final layer, and verify all filesystem/config metadata.
Count added delivery cost and lost cross-image base-layer sharing. Potential
setup savings are not yet measured net gains. No lazy snapshotter is proposed by
this patch. First-use overhead around5.2s and warm overhead around0.4–0.6s remain
far from the product target.
