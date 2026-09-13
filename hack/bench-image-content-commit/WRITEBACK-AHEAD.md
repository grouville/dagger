# Writeback ahead: storage improvement, mixed whole-command results

2026-09-13 checkpoint. **Data only, not a shipping engine fix.**
This branch does not activate the local containerd experiment described below.
All representative flow medians still lose native Cargo; the product goal is
unmet. The independently audited CSVs preserve every observation.

## Context and experiment

The previous inode-matched diagnostic attributed about 173ms of a normal 175ms
content pre-sync to file-data writeout/wait. The candidate submits completed
8MiB chunks for Linux WRITE-only writeback while content arrives. This aims to
overlap disk writeout with transfer/unpack, not eliminate durability. No worker,
extra buffer, background goroutine, persistent CLI session, or cache policy.

Metadata preSync, local fileSync, directorySync, digest/size checks, publication
ordering, leases and error propagation remain. Unsupported platforms/syscalls
fall back to existing final-sync behavior. Real hint errors remain sticky through
Sync/Commit; actual successfully written bytes drive offsets/ranges. The same
candidate includes a separately identified existing partial-write offset bug fix
(use n, not len(p)); do not call this a pure scheduling-only source change.

WRITE-only can itself block and is not a durability guarantee. Cancellation after
an accepted hint returned is tested; interruption inside a blocked kernel syscall
is not established. There is no claim of maintainer approval or universal benefit.

## Full-flow results, milliseconds

Three independent AB/BA/AB engine pairs, same two-layer gzip image bytes in both
arms. A is the commit-instrumented engine; B adds local writeback/offset changes.
Each exact/app/library run has three observations, not three independent pairs.
Summarize those within each run before taking the three-run median.

| Flow | A Dagger | B Dagger | B native | B paired native overhead | Paired CLI saving A-B |
| --- | ---: | ---: | ---: | ---: | ---: |
| First check, engine provisioning included | 12563.974 | 12487.002 | 6704.535 | +5788.976 | +269.941 |
| Exact unchanged | 515.514 | 514.540 | 120.276 | +382.620 | +7.101 |
| Application edit | 917.133 | 902.458 | 292.390 | +612.802 | +2.712 |
| Workspace-library edit | 1072.058 | 1072.505 | 469.755 | +608.645 | +1.600 |
| Actual bstr 1.12.0 -> 1.13.0 upgrade | 2289.206 | 2263.488 | 1719.829 | +543.659 | -32.890 |
| Exact after upgrade | 513.208 | 515.511 | 140.144 | +396.896 | +4.242 |

Columns are different statistics and need not subtract exactly. In particular,
the external-upgrade marginal medians look faster but its median paired CLI
difference is a 32.890ms regression. Small warm differences are not evidence of a
meaningful dev-loop win; exact/app paired native-overhead changes also regress
10.420/12.137ms. Warm overhead remains roughly 0.4–0.6s.

| Pair | A first CLI | B first CLI | CLI saving | Native-overhead saving |
| --- | ---: | ---: | ---: | ---: |
| AB | 12233.028 | 12487.002 | -253.973 | -23.633 |
| BA | 21397.872 | 12806.536 | +8591.336 | +8282.461 |
| AB | 12563.974 | 12294.033 | +269.941 | +389.032 |

Two of three CLI pairs improve; one regresses. The median paired saving is
269.941ms, whereas subtracting marginal medians gives 76.972ms. The middle A run
has a storage/lifecycle stall; its 8.591s difference is retained, not all assigned
to writeback or claimed as reliable tail elimination. One native dependency
upgrade took 3055.361ms versus Dagger 2523.346ms; the other native upgrades took
1615–1720ms. This isolated win is retained, not generalized.

Normal final-layer preSync fell 147.078/163.190ms -> approximately 4.8–5.1ms.
Corresponding image-envelope savings were 82.398/125.437ms. The slow control's
parent/final preSync took 1371.479/5570.658ms. All final barriers remain; second
local fileSync is roughly 0.04–0.10ms. Phase spans overlap: do not sum their savings
or equate a shorter preSync with the whole CLI delta.

## Reproduction and validation

Frozen local cohort: /tmp/dagger-writeback-flow-ab-b09v757_. Controllers:
/tmp/dagger-writeback-flow.9ggQwsSe. Workload is pinned ripgrep
3fce3b5bb0236da2df6d99672afb8a719642eca7, Rust 1.97.1 minimal+rustfmt,
cargo check --workspace --locked. The module performs checksum-based rsync into
locked source/target caches, then that same Cargo command.

The controller creates a fresh owned engine/volume through the ordinary CLI
image driver inside the first timer. Commands are dagger --profile check
rust:check for cold/upgrade and dagger check rust:check for warm. The sequence is
first -> exact -> three novel app/library edits -> actual manifest/lock dependency
upgrade -> followup -> compile failure/repair/old-source revisit -> restart hit.
Local post-timer diagnostics cannot substitute for actual timed-process evidence.

The retained run-pairs.py --execute, analyze.py COHORT, audit-ordinary.py COHORT,
commit-summary.py COHORT, phase-summary.py COHORT and summarize.py COHORT produced:

- Six successful flows; 36 wcprof captures with structural/declared-received-span
  gates, zero rejected, cold replay drift -0.0% to -0.1%; 18 cache analyses,
  36 affected-crate audits and 54 actual ordinary timed-execution audits.
- All 316873658 compressed bytes and both complete tar diffIDs verified in each
  fresh engine. 12 observed content commits preserve both file syncs/directory
  sync. Exact/restart reuse executes no Cargo/image transfer; edits rebuild the
  native-equivalent affected crates. External versions/memchr reuse are checked.
- 13 focused local-content/metadata race-test groups, no skipped groups; actual
  short-write baseline failure/candidate pass. Linux ARM64, Darwin ARM64 and
  Windows AMD64 test-binary compilation passes, not runtime validation.
- Source-built engine-dev targeted integration: three real-private-stream race
  roots, container export and Docker import; five roots/six export subcases pass.
- Subsequent 20MiB real-layer cancellation fixture passed three race repetitions
  after the actual writer accepted an 8MiB writeback hint. Original failed
  pre-test archive identity gate is retained; retry verified manifest/config/all
  layer identities rather than bypassing it. A content-GC warning for an absent
  content/blobs directory remains: private-snapshot reclamation passed, not a
  claim of warning-free GC or general ingest-store cleanup.
- Owned resources removed and original host container inventory restored;
  source hashes and retained engine identities unchanged.

Historical limitation: engine A/B order alternates, but native cold always runs
AFTER Dagger in this cohort. Do not attribute later improved native-order
alternation to these timings. Cold/upgrade are profiled; ordinary warm commands
still export local OTLP. Native is docker exec with a preinstalled matching Rust
image, not bare-host Cargo. CLI/engine/native images/module/local registry are
preinstalled; page/CDN caches are not purged. Both runtimes inherit unpublished
verified-stream/readiness experiments plus perf23/perf24, not clean main.

No complete installation/public-registry/auth/macOS/remote/artifact/fmt/clippy/
test-command performance claim. Initial toolchain config is handled; this flow
does not establish configuration-edit invalidation. The owner-specific harness
and runtime are not yet a turnkey public reproduction. No raw telemetry,
private analyzer, credentials or image publication accompanies this checkpoint.

## Provenance

Upstream main reverified 7c35e6274737acff0f6bd76614abb5e04efa7d12. Parent source
503d3410ef3df63fa6bc7a55c5c2453c4951c2c2, with frozen non-HEAD hashes.

| Evidence | SHA256 |
| --- | --- |
| Control engine image | 562e6967b70539c267c395338bdf57acaa0f1dd8d8fad660f7888606aaf2ae4e |
| Candidate engine image | bdbf018f39c7996367b0311654707cedaa4b22e8349fafd2881f362dd3ee035d |
| Candidate build receipt | 6124cb089a266d1883d75d835b3f79955bd512307efc832060841ee297a825a7 |
| Full-flow summary | 53f5b97f5ceb343c4e17920084130ea3c616ec463bbee32778605ec8a7900d8b |
| Commit summary | 9259364b5a8309a6fdf0a300e22ea9864a14dda79cecb3447877514e8657ec2e |
| Profile analysis | 945e8e1adae2bbfeb791699a68360e90486973fc744b5eb84066905ccccc422d |
| Ordinary execution audit | 9c11571ca37f438632f9a52f308478a2529ac6561fe3378a3a7bfa761701f292 |
| Supported integration | 1c5c3a4d164c91a8a8ca01eda2b33bd2a9fc282f646557ba18d392ed84dc9e47 |
| After-hint cancellation retry | cff2c84c295c0fcbb024aec8b397754046f6fd06ea1be62a7dadc15637e8b59d |
| Local raw OTLP, 43281375 bytes | f7b5864cf3f092eb1b29f8487a437a8f6477e1c828202becca33c4b5b65c55f7 |

Next: ordinary complete prepared OCI toolchain packaging, with correct module
integration and all delivery included. Shared-base reuse costs and full user
workflows still need measurement. Do not promote this mixed writeback result as
the cold-start solution.
