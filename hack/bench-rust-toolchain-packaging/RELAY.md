# Bounded stream relay: image-phase gain, no convincing end-to-end win

2026-09-13. **Data-only experimental checkpoint, not a default engine fix.**
Correctness gates pass, but the median paired cold-command saving is only
45.144431 ms; native-relative overhead worsens by 35.627685 ms. Every flow median
still loses native Cargo. This does not meet the Rust developer-loop goal.

This is a new, independent engine A/B cohort. The [README matrix](README.md)
is the earlier perf26 packaging comparison; [STREAM-COST](STREAM-COST.md) is
the subsequent attribution diagnostic. Do not add their reported differences
to this experiment or compare different cohorts as a controlled improvement.

## Hypothesis and implementation tested

The diagnostic found producer pipe waiting alongside hashing and extraction.
Test whether bounded producer/consumer overlap improves the complete workflow,
without treating overlapping waits as recoverable wall time. A retains engine
562e; B adds a four-buffer relay to that same source. Both use the identical
complete flat standard Zstd image and prebundled-rsync Rust module.

Fresh offset-zero streamed layers >=8 MiB use four reusable 1 MiB copied buffers;
small streams, existing blobs and resumed downloads retain their previous paths.
The worker is joined before accepting a private applied result. Full compressed
and uncompressed digest checks, real content writes, final syncs, cancellation,
error propagation and private-snapshot ownership remain. The uncompressed hash
queue is unchanged. No new OCI format, lazy snapshotter, egraph/cache identity,
Cargo action, public CLI lifecycle or listener is introduced.

This depends on earlier **unpublished local streamed-import/containerd** and
readiness experiments. Neither arm is clean main, and neither includes the
separate writeback-ahead candidate. This checkout publishes documentation and
CSV projections, not those runtime dependencies or an upstream-approved patch.

## Complete-flow results, milliseconds

Three independent fresh-engine pairs, AB/BA/AB. Native/Dagger cold-command order
also alternates by pair. Exact/app/library have three observations per run;
upgrade/followup have one. Columns below are marginal medians of within-run
medians; overhead and ratios are computed per native/Dagger observation before aggregation.
The final column is the median of three paired A-minus-B differences. Positive
savings favor B. Columns therefore need not subtract exactly.

| Flow | A Dagger | B Dagger | B native | B overhead | B/native ratio | Paired CLI saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| First check + provisioning | 11332.855 | 11086.951 | 6986.299 | +4482.015 | 1.55x | +45.144 |
| Exact unchanged | 514.435 | 530.834 | 118.652 | +396.761 | 4.28x | -16.398 |
| Application edit | 906.433 | 887.637 | 305.437 | +580.783 | 2.89x | +18.796 |
| Workspace-library edit | 1038.672 | 1045.152 | 453.931 | +591.221 | 2.30x | +0.994 |
| Actual bstr 1.12.0 -> 1.13.0 upgrade | 2217.843 | 2228.922 | 1683.216 | +545.706 | 1.32x | -42.459 |
| First unchanged CLI after upgrade | 505.947 | 511.161 | 122.680 | +386.734 | 4.24x | -5.214 |

Subtracting cold marginal CLI medians gives 245.903272 ms, **not** the paired
45.144431 ms saving. The paired cold-overhead saving is -35.627685 ms, with only
one favorable pair. Small mixed warm differences do not establish a useful warm
win; the relay is on the cold import path, and warm commands transfer no image.

| Pair | A cold CLI | B cold CLI | Native A | Native B | CLI saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| AB | 11895.690666 | 10823.931944 | 7445.442319 | 6986.299089 | +1071.758722 |
| BA | 11332.854614 | 25328.609883 | 6563.634117 | 16450.738510 | -13995.755269 |
| AB | 11132.095773 | 11086.951342 | 6685.708403 | 6604.936287 | +45.144431 |

The slow B run is retained without trimming or host-noise correction. Its
25.328610 s CLI includes an 11.425485 s image envelope, a 10.868581 s source/Cargo
process, and an 8.109920 s `metadata.content.Commit.preSync` span inside that image
envelope. Native also takes 16.450739 s in this isolated run. The host-level
cause is not established; this is real observed latency, not grounds to discard
the sample or subtract the sync time from the score.

Image-envelope paired savings are +837.502361, -8056.692473, +446.442950 ms:
median +446.442950 ms, two favorable pairs. This is phase evidence, not an
end-to-end saving estimate. Phases overlap and must not be added together.
Source inspection places preSync around the ingest file's `fsync` path; lock
acquisition and the subsequent metadata transaction have separate spans. Kernel
syscall/off-CPU/device evidence is still needed to distinguish filesystem,
journal, device and scheduling delays. No durability shortcut is proposed.

## Correctness and protocol

- Source-built resolver/relay race tests: 29 roots, three passes each, no skips
  or races; Linux arm64 test-binary compilation passes. Normal dev deployment
  and the pinned CLI smoke query pass. An earlier deployment failed on borrowed
  Git objects; the self-contained checkout retry preserved all source bytes.
- Supported source-built integration: all five expected roots and six export
  descendants pass. All seven new relay integration roots execute three times,
  including the stock >8 MiB Zstd filesystem applier. This is not exhaustive
  platform or concurrency validation.
- All 36 maintained wcprof captures pass structural/completeness, declared vs
  received engine-span counts, and the predeclared absolute replay-drift <=2%
  gate. Observed drift is -0.2% to 0.0%; no rejected captures. All 18 cache
  analyses, 36 affected-crate audits and 60 ordinary execution audits pass.
- App edits rebuild only ripgrep; workspace-library edits rebuild the expected
  three-crate chain. Actual bstr upgrade sets match native without rebuilding
  unrelated memchr. Failure/repair/old-source revisit and engine-restart reuse
  checks pass; exact hits execute no Cargo or image transfer. Cache parsing is
  not a leak-free lifecycle proof.
- Before capture, the followup protocol was corrected in **both arms**: timed
  `dependency-followup-dagger` is now the first Dagger CLI after the upgrade,
  before `check-log` retrieval. Process order and its no-exec/no-image trace are
  audited. Post-timer debug retrieval still occurs outside timing. The earlier
  packaging cohort's followup had an intervening diagnostic CLI.
- Every cold run transfers the same full 298210801-byte layer; full decoded tar
  identity is 923695616 bytes. All six content commits retain metadata/file/
  directory sync and verified completion. Owned engines, containers, volumes
  and registry are removed with identity checks; prior inventory and retained
  engine identities remain unchanged. No global prune or host cache drop.

## Reproduction and retained projections

Pinned ripgrep `3fce3b5bb0236da2df6d99672afb8a719642eca7`, Rust 1.97.1 plus
rustfmt, `cargo check --workspace --locked`. Cold/upgrade commands use ordinary
`dagger --profile check rust:check`; warm commands use `dagger check rust:check`.
Each first CLI provisions its fresh engine inside the timer. Native is
`docker exec` with the same Rust/flags, not bare-host Cargo. Identical source
reconciliation, mutable source/target caches and Cargo registry/git caches
remain. Full toolchain/root configuration handling is retained, not edited in
this matrix.

Local harness: `/tmp/dagger-rust-relay-flow.HNDAaKR9`; captured cohort:
`/tmp/dagger-relay-flow-ab-dhu3vr_v`. On the original host, reviewed/frozen
`run-pairs.py --preflight` and `--execute` validate pins and refuse existing
outputs. A rerun requires a new owned harness/output location and the same gates,
not deleting this evidence. `analyze.py`, `audit-ordinary.py`,
`commit-summary.py`, `phase-summary.py`, then `summarize.py` consume the cohort.

CSVs are canonical JSON projections, with milliseconds at six decimal places:

| File | Data rows | Contents |
| --- | ---: | --- |
| [relay-flow-results.csv](relay-flow-results.csv) | 72 | Every native/Dagger flow observation |
| [relay-flow-pairs.csv](relay-flow-pairs.csv) | 18 | All paired run-level flow differences, including negatives |
| [relay-phase-results.csv](relay-phase-results.csv) | 6 | Every cold phase sample |
| [relay-phase-pairs.csv](relay-phase-pairs.csv) | 3 | All cold phase pair differences |
| [relay-sync-results.csv](relay-sync-results.csv) | 6 | Every cold content-commit sample and residual |

`first-check` already includes provisioning; the canonical
`provision-plus-first-check` alias is not exported as a second observation.
Flow-pair arm values are within-run medians, not additional independent samples.
Sync child durations are inclusive; do not sum them with their parents.

Not yet a turnkey public runtime repro: owner-specific harnesses, experimental
engine source and prepared OCI archives remain local. Docker, CLI, engine/native
images, modules and registry blobs are preinstalled. Release preparation and
local registry prepopulation precede timing; user image transfer/unpack remains
inside it. Host page/CDN caches are not purged. No public-CDN/authentication,
complete installation, shared-base, configuration-edit, macOS/remote, fmt/Clippy/
tests/build/artifact-export claim. No raw telemetry, private analyzer, credentials,
public image, PR or maintainer-approval claim is included.

## Provenance

Upstream main was reverified at `7c35e6274737acff0f6bd76614abb5e04efa7d12`.
Frozen source parent: `503d3410ef3df63fa6bc7a55c5c2453c4951c2c2`.
The original 1451-file non-HEAD source manifest is preserved; the complete A/B
delta is the following four changed/added resolver files, checked before and
after build/test commands. The original dirty workspace is untouched.

| Resolver source | SHA-256 |
| --- | --- |
| streamed_fetch.go | 60b7a7b4d986ecd2dbc908b3f21c9ac4f07f479fe064f67612e4182c76e30744 |
| streamed_relay.go | c5694b75f65f1bd55eee3dd0da0b6bf3c4a2ce5f5c360ab44858a75d2210ea8f |
| streamed_relay_test.go | 2291e030ea0947df87b2062218482d0447e2b952425afb02147dd6f7b2a07f9d |
| streamed_fetch_relay_test.go | 6f106ac00bd0f1cefb63e79d9a6e966017b64a388b419151b281522904b707d3 |

| Identity or retained receipt | SHA-256 |
| --- | --- |
| Control engine image | 562e6967b70539c267c395338bdf57acaa0f1dd8d8fad660f7888606aaf2ae4e |
| Relay engine image | 7a27d40095e98dbb45f7d3ac5faa0d210c535de1ef2338ff11675c970702fe20 |
| Same CLI in both arms | 6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad |
| Same flat image manifest | 20589cc18d29e396e1299bd970a268de68016a4973b0ae1ff92162c99d3c3427 |
| Same main.dang | 90fde261a47bef51bac16b5d24f26f9715e7dceb498e3c420837b9b651314b0e |
| Same dagger-module.toml | 80ceb12a068bb2c86041ba35bdcb24edada8ae228b77450de2ce917caa2ec8e5 |
| Control build receipt | 86284135ca90b89e4a405f1ffafebb63c67d38002225e73c92566364b58cd2b5 |
| Relay build-r2/build.json | 257604b0cd181a4cb257817dcd5f01e92e90a429e4113966a353bd56f3fbbc0f |
| Relay source-copy.json | 805c29a95e9b827e2c8eb721ee3d15a9e64bb756329fa998c6f2016b64dedc74 |
| Relay supported-r1/stage.json | 0dbe2f05a47597d6db8fdc29ce7f2d9ed2d8493ac9c062bdbd6f6556f713889d |
| Full-flow summary.json | e3c428253465a636b24b37bf6ec72620bdc3da2c93428553e91a51a856734575 |
| phases.json | e27dbda69f783329a5cb8a687238d98601d0ec4563abe8d175363ec3f859a9c7 |
| commits.json | f57d6cddaac48254f2fb16d6abea46604e6ec9e61c7ae8b5e8e5291233aa2856 |
| Cohort receipt | f133566529b211035b36bd2b5a329639d7b220da312c7d69c7dce0eda5da5a04 |
| wcprof/execution analysis | 957fc4be9e004e71ba55bd4f17d5f32207d230714673d4a6188014fe15dad2ba |
| Ordinary execution audit | 60c34245fb45e46b4615946c0dbb79734e83a4d6120338a8f1b48539d1f3a299 |

Engine receipts are retained under `/tmp/dagger-stream-relay-engine.2UZDettN`;
control receipt is under `/tmp/dagger-content-commit-trace.Lvt6a9m7`. Historical
prepared/flat parity approval remains
`73b991879f5021721a24177983418cf843574497bf35269d26a6e9d18414d79f`.
Historical base/flat packaging differences are not differences between these
two arms. Passing this experiment's correctness gates does not justify enabling
the relay by default; end-to-end and tail performance remain the next decision.
