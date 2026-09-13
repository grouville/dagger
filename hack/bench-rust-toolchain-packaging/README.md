# Prepared Rust OCI image: measured cold improvement, remaining UX gap

2026-09-13. **Benchmark checkpoint, not an activated production change.**
Stacked on perf/rust-25-cold-content-diagnostics, commit db870fc60. No engine or
module implementation is changed by checking out this branch. No PR or public
image was created. This records a standard image-packaging experiment and all
results, not a claim that the official Rust module is finished or faster than
Cargo. Every representative flow median still loses native.

Follow-up [stream-cost diagnostic](STREAM-COST.md) attributes the remaining
image phase using wcprof plus CPU/runtime traces. It is not a new speedup or
replacement for this ordinary first-CLI scorecard.

## Hypothesis and implementation tested

Avoid runtime package installation and extra layer application by preparing the
complete supported toolchain image once at release time. A uses the original
two-layer gzip Rust image plus runtime pinned rsync/libpopt installation. B uses
the complete prepared filesystem in one standard OCI Zstd layer and a module
variant that removes ONLY the already bundled rsync installation. Both still
resolve the project's root toolchain configuration before edit-sensitive source,
then run exactly the same Cargo action/cache mounts. Requested rustfmt is bundled,
not omitted. No project sources, crate caches or target outputs are prebaked.

Publisher preparation uses existing go-containerregistry v0.21.4 mutate.Extract,
tarball.LayerFromFile with Zstd level3/SpeedDefault, mutate.Append and layout
APIs. It spools the full tar to disk, preserving filesystem metadata; no custom
layer applier, lazy snapshotter, timestamp normalization or removed components.
Runtime config is preserved except base WorkingDir absent -> effective default
'/' (both actions explicitly set /src). Prepared-to-flat runtime config is exact;
OCI history/rootfs necessarily change. This is packaging PLUS codec PLUS module
integration, not a compression-only experiment.

Both arms use the SAME diagnostic engine 562e and CLI 6a5. The separate writeback
candidate is not included, and its measured savings must not be added here.
Each first standalone CLI creates its own engine/volume and includes all image
transfer, decoding/application, setup, source sync, Cargo and shutdown.

## Complete results, milliseconds

Three independent AB/BA/AB pairs. Native/Dagger first-check order also alternates
by pair (native first, Dagger first, native first). Three within-run observations
for exact/app/library do not create nine independent pairs. Warm columns are
medians of within-run medians; differences/ratios are computed before medians.

| Flow | A Dagger | B Dagger | B native | B paired overhead | B/native ratio | Paired CLI saving A-B |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| First check + provisioning | 12712.740 | 11427.862 | 7071.815 | +4063.766 | 1.56x | +955.774 |
| Exact unchanged | 511.501 | 520.316 | 121.931 | +389.739 | 4.05x | -19.039 |
| Application edit | 909.033 | 891.481 | 294.490 | +592.600 | 3.01x | +17.106 |
| Workspace-library edit | 1040.694 | 1035.907 | 472.531 | +571.628 | 2.21x | +5.313 |
| Actual bstr 1.12.0 -> 1.13.0 upgrade | 2208.660 | 2186.197 | 1691.323 | +476.367 | 1.28x | +22.463 |
| Exact after upgrade | 535.331 | 502.736 | 125.549 | +377.186 | 4.00x | +30.497 |

Columns need not subtract exactly. The cold paired saving median is 955.774ms;
subtracting the marginal medians gives 1284.878ms, a different statistic. No warm
win is established: unchanged gets slower, while other paired differences are
small and variable. Warm overhead remains roughly 0.4–0.6s, not tens of ms.

| Pair | A cold CLI | B cold CLI | Native A | Native B | CLI saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| AB | 12712.740 | 14112.874 | 7366.129 | 10049.107 | -1400.134 |
| BA | 13259.889 | 11023.591 | 6768.503 | 7071.815 | +2236.298 |
| AB | 12383.635 | 11427.862 | 6489.479 | 6774.274 | +955.774 |

Two of three CLI pairs improve. The first B run includes a 3.214s docker-run
span versus 0.329s in its A comparison; B connect totals 3.893s. Its native command
also takes 10.049s while Cargo reports 6.15s. These observations remain in the
scorecard; we have not established the host-level cause or a reliable tail fix.
The second A Cargo/source process is 923ms slower than B, so its whole 2.236s
saving must not all be attributed to packaging.

Cold image envelopes improve in all three pairs: A 4001/3905/3871ms versus
B 3372/3357/3331ms, saving 630/549/541ms. Runtime dpkg A 206–270ms disappears only
because the exact packages are included in B's transferred bytes. Root-config
rustup execution remains, falling from 640–671ms to 79–88ms. Cargo work is retained.
These phases overlap; do not add their median savings as a causal CLI estimate.

## Correctness, profiling and reset boundaries

- Fresh engine stores, native workspace/container and XDG CLI state per run.
  No listener or shared resident CLI session. All six ordinary flows completed.
- All 36 wcprof captures pass structural completeness, declared/received engine
  span equality and the predeclared absolute replay-drift <=2% gate; observed
  drift is -0.0% to -0.1%. No rejected captures. 18 cache analyses, 36 affected-crate
  audits and 54 actual ordinary timed-execution audits pass.
- App edits rebuild only ripgrep; workspace-library edits rebuild the expected
  three-crate chain; native and Dagger match. Actual external bstr versions and
  unchanged memchr reuse are checked. Failures/repair/old-source revisits and
  restart reuse pass. Exact/restart hits execute no Cargo/image transfer.
- Full compressed bytes and full decoded tar diffIDs are verified before capture
  and all compressed transfer progress converges inside every cold CLI:
  A 316873658 bytes/two layers; B 298210801 bytes/one layer. Nine cold content
  commits retain metadata/file/directory sync and verified publication ordering.
- Independent read-only actual-import inventories match all 7294 logical paths:
  content, modes/ownership, non-root mtime, xattrs, symlinks and visible hardlink
  groups. Portable archive root metadata is separately preserved. Raw external
  st_nlink/root-runtime-mtime differences remain disclosed, not bit-identical stat
  parity. Six actual compiler/component/package outputs match prepared/flat.
  A first flatten recipe omitted the explicit root header and was rejected;
  that failed receipt remains separate rather than redefining its result.
- All owned benchmark containers/volumes and registry removed with identity
  checks; initial host container inventory restored. Retained engines/source
  hashes unchanged. No global prune, page-cache drop or host security changes.

Initial toolchain config handling is tested, NOT configuration EDIT invalidation.
Cold and dependency-upgrade commands use --profile; ordinary warm commands omit
it but retain local OTLP. Post-timer debug/crate retrieval is not included in
headline latency and cannot replace actual timed-process execution evidence.

## Reproduction and limits

Pinned ripgrep 3fce3b5bb0236da2df6d99672afb8a719642eca7, Rust 1.97.1 minimal+rustfmt,
cargo check --workspace --locked. Ordinary commands: dagger --profile check
rust:check (cold/upgrade), dagger check rust:check (warm). Native is docker exec
with the same Rust version/flags, not bare-host Cargo. Source reconciliation is
rsync -rclp --delete /input/ /src/, with locked mutable source and target caches
and ordinary Cargo registry/git caches. B changes only prebundled package setup.

Local frozen controller owner: /tmp/dagger-rust-packaging-flow.UDrhLJfV.
Captured cohort: /tmp/dagger-packaging-flow-ab-ey71od7e. Standard image recipe and
independent correctness receipts: /tmp/dagger-rust-flat-toolchain.j3nNu4PD/standard.
After the pinned parity/OCI/hash gates, the retained run-pairs.py --preflight and
--execute run the six flows; analyze.py, audit-ordinary.py, commit-summary.py,
phase-summary.py and summarize.py take the cohort path. No speedup acceptance
gate; all output rows and failures are retained. CSVs here are canonical JSON
projections at six decimal places, independently audited: 72 flow/6 phase/9 sync.

Not yet a turnkey public runtime reproduction: owner-specific controllers,
engine experiments and OCI archives remain local. Publisher preparation and
local registry prepopulation happen before timing; all end-user delivery is
inside the first command. Docker, CLI, engine/native images and module source
are preinstalled. No public-CDN/authentication/complete-installation/macOS/remote
or fmt/clippy/test/build/artifact-export performance claim. Host page/CDN caches
are not purged. Both arms inherit unpublished stream/readiness experiments plus
perf23/perf24; not clean main versus a publicly activated production stack.

Shared-base-present comparison remains required: flattening loses original
base-layer reuse. A benefit with empty engines is not a universal packaging
recommendation. Official image/version/platform ownership and release integration
also require design/review; no maintainer approval is implied.

## Provenance and next bottleneck

Main reverified 7c35e6274737acff0f6bd76614abb5e04efa7d12 before capture. Frozen
engine-source parent 503d3410ef3df63fa6bc7a55c5c2453c4951c2c2, non-HEAD hashes
verified. Same engine image 562e6967b70539c267c395338bdf57acaa0f1dd8d8fad660f7888606aaf2ae4e.

| Receipt | SHA256 |
| --- | --- |
| Full-flow summary | 896ea0d1984564040e5b52eeb2770d129b7d79581c9cf336d001ad73d13d58f3 |
| Phase summary | bcf16242075eaf97b5c614de4aee101f92de445b3f4d43a584e687679f1728b0 |
| Commit summary | ae8301154007bcbcc12924af4f63b56d878c43b1bfebc4768c38e09ba26cafcb |
| Cohort | e9baa196a489cd5a31e50cbd424517e31dd3acdec229ebc93093befb8cf67501 |
| Profile analysis | 3fa05af1a867a62e0ea9c7b2d193c0f4fa6b1458361033cce0bae67db3e60003 |
| Ordinary execution audit | d16c45fd8af40d700a49378785ddaa37b25f84d5b294f43ad31ff2c74f00dcfa |
| Parity approval | 73b991879f5021721a24177983418cf843574497bf35269d26a6e9d18414d79f |
| Standard OCI archive | ac6e84e096f3f2e90a8864c043fe9c3f57fa405a245cadf9b33b608e95b5d495 |
| Raw local OTLP, 40814722 bytes | 232e63d645f30d7964ca81ae3894a80ab82fac004dcf15fcdfd2ce1bee6dc9ca |

About 3.1s in HTTP GET remains, but that span lasts through response-body
consumption: synchronous verified content writes and pipe backpressure from
decoding/extraction can extend it. It is NOT proof of 3.1s network latency.
Next diagnostic: separate aggregate response-read/content-write/pipe-wait time,
aligned with CPU/runtime profiling, while retaining the same whole-CLI scorecard.
No proposed buffering or network fix is yet a measured saving.
