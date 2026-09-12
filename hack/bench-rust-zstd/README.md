# Compression-only Rust image experiment

Performance first; active goal is not achieved. No engine snapshotter, cache,
verification or module semantics are modified. The image changes only its
compressed representation using Dagger's existing `Container.Export` option
`ForcedCompression: ImageLayerCompressionZstd`. This is a standard
[OCI layer media type](https://github.com/opencontainers/image-spec/blob/main/media-types.md).
Public registry compatibility and remote/macOS performance are not certified.

Source and runtime pins: upstream main 6bf59d50654ce9244ebeee1cc090b7dce3fe3083,
reviewed db9d005c715ac9d146780d783faf7f7b55d23e5e engine image3df4828f, identical
CLI98fc6ea8 on both treatments. User worktrees and prior experimental engines
are preserved. The separate socket candidate is NOT included.

## Offline size and stock-applier diagnostic

`prepare.sh` streams the exact original large-layer tar into zstd1.5.5 at
levels3 and10, with two compression workers. Both outputs decode to the original
837738496-byte tar and diffID7dfc1d91. No headers, padding, files, licenses or
metadata are modified. Preparation runs outside end-user timers.

`run-apply.py --execute` used nine sequential network-disabled disposable
containers in ABC/BCA/CAB order; stock containerd2.2.5 applier on all treatments,
same binary, original engine igzip decoder for gzip. Input verification is
before timing, hence hot source page cache. Output is fresh each time.

| Encoding | Compressed bytes | Median local apply s | Median block saving s |
| --- | ---: | ---: | ---: |
| Original gzip | 288641068 | 3.786337 | — |
| zstd CLI level3 | 267932102 | 2.591683 | 1.180156 |
| zstd CLI level10 | 239051435 | 2.571708 | 1.214629 |

Both alternatives faster in3/3 blocks. Ranges1.111–1.253s and1.172–1.267s.
All returned identical diffID/tar size and3061-entry output inventories covering
bytes, mode, owner, mtime and symlink target. Exact tar equality also preserves
input hardlink/xattr metadata, but output hardlink topology/xattrs were not
separately audited. All nine owned containers removed and absence verified.

These are NOT full Dagger timings: no downloads, snapshot commits, CLI/module,
Cargo or output export. Hashing of unchanged837.7MB input remains required.
No addition to previous streaming or pipelined-hash cohort gains is permitted.

## Existing Dagger exporter candidate

The retained `build-image.go` compiled against the frozen SDK then ran through ordinary
`dagger api with-session` on retained publisher engine3b711dbd. This is fixture
preparation, not timed installation. The code modifies no project/toolchain
content and does not run Cargo. No external image publication occurred.

The API's default zstd output is **different from both CLI-level trials**:
294925737 compressed layer bytes versus original316873658;21947921 bytes
saved (~6.9%). Do not claim the CLI-level10 size for the exported API candidate.
The base and zstd exports have deeply identical parsed image configurations,
two layers each, and matching fully decoded sizes/digests for both layers:
77895680 and837738496 bytes. `oci.json` records every actual descriptor and
verification result. It is not sufficient to compare declared diffIDs alone.

First builder compile used an incorrect SDK enum name; corrected to the actual
generated `ImageLayerCompressionZstd`, with failure and successful logs retained.
The standard export completed. No API/engine change was needed for this fixture.

The published `image-builder.go` differs only in accepting `--output-dir`
instead of the original fixed scratch path. The directory must already exist,
and outputs must not exist. It retains the exact image/platform/compression
recipe. Publisher-side setup, not a developer's first-check timing:

```sh
go build -o /tmp/rust-zstd-builder ./hack/bench-rust-zstd/image-builder.go
artifact_dir=$(mktemp -d /tmp/rust-zstd-artifact.XXXXXXXX)
dagger api with-session -- /tmp/rust-zstd-builder --output-dir "$artifact_dir"
```

The published builder compiled on the direct-main branch, rejected missing
arguments and pre-existing outputs, and passed the standard session/export
path. Its newly exported OCI archive was byte-identical to the measured one:
SHA256 fbe805fd31e9dfaf56196f1d032a32e34f4f77e7ee3c20e4a20dbb2b83f6d326.
Publisher cache reuse here is fixture validation, not a cold-user measurement.

## Full-flow measurement

`run-pairs.py --execute`: three independent AB/BA/AB engine-cold pairs. Same
owned loopback-only registry and bridge for both original gzip and API zstd;
same engine, CLI, module, toolchain configuration, source and Cargo flags.
Both registry fixtures prepopulated before timers; no claim about public/CDN
delivery or complete installation. Native is docker-exec Cargo in its existing
matching Rust image, not a bare-host invocation. Host page caches not purged.

Each run covers first check,3 exact/app/library repeats, real bstr1.12→1.13
upgrade and followup, failures/repair/revisit, and engine restart. Last pair
also checks toolchain-component/config transitions after timed measurements.
Cold and upgrade commands profiled; ordinary warm checks unprofiled. Complete
raw telemetry and retained command logs feed maintained wcprof after execution.

`analyze.py COHORT` retains 36 full capture/actual-exec/native-crate gates,
18 post-timer cache analyses and 36 strict ordinary warm crate audits. Each
image must transfer/unpack every byte from its independently verified descriptor
set exactly once. Compressed sets intentionally differ; verified config/tar
equality is the semantic invariant. Ordinary app edits require only ripgrep;
later post-failure recovery diagnostic requires its actual three-crate history.
`summarize.py COHORT` summarizes repeats within run before paired comparison.

## Completed fresh comparison

The corrected cohort `/tmp/dagger-rust-codec-ab-atref5tv` passed all 36 complete
wcprof captures, 18 cache analyses, 36 ordinary warm crate audits and the two
final-pair configuration-transition sequences. Replay drift was −0.0% to
−0.1%, including cold captures. The receiver stopped; owned resources from
both cohorts were independently verified absent after cleanup.

Positive savings mean zstd was faster. These are three independent paired
per-run summaries; warm repeats are not nine independent experiments.

| Flow | Median paired CLI saving ms | Range ms | Favorable pairs |
| --- | ---: | ---: | ---: |
| First check, profiled | 1,986.577 | 980.402 to 2,535.265 | 3/3 |
| Provision plus first check | 1,974.997 | 943.218 to 2,565.257 | 3/3 |
| Exact unchanged | 16.278 | 2.423 to 44.606 | 3/3 |
| Application edit | 13.019 | −18.599 to 26.972 | 2/3 |
| Workspace-library edit | 30.949 | −5.085 to 33.955 | 2/3 |
| External upgrade, profiled | −10.341 | −25.904 to 41.780 | 1/3 |
| Upgrade followup | 8.255 | −0.310 to 76.319 | 2/3 |

wcprof supports a repeatable **cold image-path** gain: paired delivery savings
1.375–1.480 s, median 1.457 s; unpack savings 1.319–1.392 s, median 1.357 s.
Connections were closely matched within pairs (−22 to +12 ms saving), including
one pair where both took about 1.5 s. Cargo timing varied: candidate was 519 ms
faster, 455 ms slower and 886 ms faster. Do not attribute all of the full CLI
gain to compression, sum phase medians, or add previous experiment savings.

Candidate first-check median: **13.079 s**; provision plus first check:
**13.335 s**. Median paired per-run overhead over native remained **7.061 s**
including provisioning. Native-normalized provision-plus-first improvement was
1.195 s median, range −0.669 to +3.035 s, favorable only 2/3. The cold goal is
still far away, even on this local registry. All candidate flows still lose to
native: exact 438 ms, app edit 829 ms, library edit 988 ms, upgrade 2,173 ms,
followup 429 ms. Warm overhead remains roughly 0.31–0.54 s.

**Keep the cold codec improvement; do not claim a warm-loop improvement.**
The external-upgrade CLI regressed at the paired median; native-normalized
exact and followup overhead also regressed by about 9 and 4 ms. Warm paths do
not decode the image again, and mixed small differences lack codec attribution.

This is a toolchain-publishing option supported by existing Dagger APIs, not a
new engine mechanism or a shipped official-module default. No public-registry
image was uploaded. No artifact/fmt/Clippy/test-command/macOS/remote performance
score is claimed. Public delivery and combination with other engine changes
require their own measurements.

Evidence in this branch: `comparison.json`, `phases.json`,
`image-validation.json`, `profile-validation.json`, and `local-apply.json`.
The comparison omits bulky duplicated profile details, retained locally.

- Full local summary SHA256:
  059e91390b7ba63d0192cece5ec4278983d573e5cbba8cce34bbe45c6f5b6e6c.
- Full local wcprof report SHA256:
  cf674c151d0569ca115b4bd563ff7bc5eb8fb173cd73c0f5320deb50993ef77b.
- Raw local OTel: 46,078,787 bytes; SHA256
  9ff0cc7989bbac51b7a8f922b2b8aa11e43c305d8f7a0a57c5b1c2292610bcae.

Raw telemetry and the private maintained analyzer are not published.

## Retained rejected first cohort

`/tmp/dagger-rust-codec-ab-95xzkpeg` completed all six timed sequences, but the
last post-timer configuration check failed an inherited benchmark expectation:
it expected the prior prepared image's bundled rustfmt after removing the root
configuration. These compression-only images have identical minimal toolchains;
both correctly contain Cargo, rustc and rust-std without bundled rustfmt/Clippy.
The immutable component file confirms this. No product code was changed.

The first analyzer also inherited an incorrect exit expectation: deliberately
invalid toolchain configuration is expected to exit 1, not 0. Both benchmark
errors were found during bounded source review. The original sources, failed
cohort status and all 46,113,278 bytes of raw telemetry remain unchanged; raw
SHA256 77909c0a2a140a4790b780fe811b719f4fe34f5efca103ff7b7257295339367a.
No complete before/after speed claim is accepted from that rejected cohort.

Fresh retry owner: `/tmp/dagger-rust-zstd-r2.CeRkzU9i`. It uses the exact same
images, module, engine and CLI. Only the post-removal expectation changes to
the same empty optional-component set for both sides; analyzer explicitly
recognizes the deliberate invalid-config failure and requires all four
component-state gates in each final-pair run. New stores, registry, receiver
and telemetry output; no reuse of failed benchmark state or overwritten data.

Retained exact full-flow reproduction commands (single-use owned paths; choose
a new owner/namespace rather than overwriting either completed cohort):

```sh
python3 /tmp/dagger-rust-zstd-r2.CeRkzU9i/run-pairs.py --execute
python3 /tmp/dagger-rust-zstd-r2.CeRkzU9i/analyze.py COHORT
python3 /tmp/dagger-rust-zstd-r2.CeRkzU9i/summarize.py COHORT
python3 /tmp/dagger-rust-zstd-r2.CeRkzU9i/phase-summary.py COHORT
```

These full-flow scripts and raw captures remain in the shared workspace. This
branch publishes the reusable image recipe and results; it is not the final
portable end-to-end Rust demo required by the larger goal.
