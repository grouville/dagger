# Rust image SHA-256 backend calibration: no useful gain

2026-09-14. **Rejected backend experiment, not an engine change or CLI win.**
The [ordinary Rust scorecard](../bench-rust-toolchain-packaging/RELAY.md) remains
unchanged and the product goal remains unmet. No engine was rebuilt for this
experiment. This standalone Linux calibration does not select Dagger's backend.

## Why test this

[wcprof and aligned CPU/runtime diagnostics](../bench-rust-toolchain-packaging/STREAM-COST.md)
identify SHA256 AVX2 in 361/745 image-phase samples on the measured i5-9300H,
which lacks SHA-NI. Those CPU shares are not removable wall time. The existing
engine already pipelines full uncompressed hashing with extraction; this is
not another measurement of that earlier scheduling change.

Pinned Go 1.26.8 includes BoringCrypto behind an experimental build option.
The calibration asks whether it provides useful backend headroom through the
same `crypto/sha256.New` API, verifying all the same image bytes. Both arms use
CGO_ENABLED=1 and GOMAXPROCS=2; only the Boring arm adds
GOEXPERIMENT=boringcrypto. Dynamic hash type and build settings confirm the
intended implementation, rather than silently measuring the same fallback.

BoringCrypto has Linux/CGO and FIPS-mode restrictions. It is **not** proposed as
an engine-wide compiler flag or cross-platform shipping solution. No digest
algorithm, expected hash, verification, durability, isolation or cache changes.
The inspected [MinIO SHA implementation](https://github.com/minio/sha256-simd/blob/master/sha256.go)
falls back to the standard library for this host's feature set; its separate
AVX512 multi-message interface needs different hardware and independent messages.
We did not claim or benchmark a MinIO speedup from its general README figures.

## Results

Six sequential alternating AB/BA pairs. Each treatment hashes the full
compressed blob and full uncompressed tar with 256KiB writes. Four separate
preflights prepare/verify inputs; two deliberately incorrect expected-digest
runs fail. Page cache is not purged. All 24 timed observations are retained in
[samples.csv](samples.csv), including regressions.

Milliseconds; positive paired savings favor Boring:

| Prepared input | Default median | Boring median | Paired saving [min, max] | Favorable |
| --- | ---: | ---: | ---: | ---: |
| Compressed, 298,210,801 bytes | 683.377 | 680.722 | +1.588 [-2.398, +6.740] | 3/6 |
| Uncompressed, 923,695,616 bytes | 2104.049 | 2104.316 | -1.658 [-19.782, +18.169] | 2/6 |

This table times **read + hash + finalization**. External process time also
includes initialization/self-tests, open/stat, allocation, comparison and output.
Its paired savings are -0.706ms compressed and -3.818ms uncompressed. Median
paired Boring/default external ratios are 1.001035 and 1.001815 respectively.
Process CPU over the read+hash interval, including C execution, regresses
18.725ms and 70.589ms paired;
0/6 CPU pairs favor Boring for either input. Marginal medians need not subtract
to the median of paired differences.

**Disposition: no useful backend gain demonstrated; do not adopt or rebuild an
engine on this evidence.** This rejects this route on this workload/host, not
every SHA implementation or other hardware. These serial prepared-file times
must not be summed or subtracted from a concurrent image-import critical path.
No download, decompression, extraction, source sync, Cargo or CLI UX is measured.
The compressed writer's usual engine buffer is 1MiB, not this calibration's
256KiB; the latter matches the existing uncompressed hash worker. No performance
claim for macOS, remote engines, first installation, checks or exported builds.

## Correctness and provenance

- Every timed/preflight blob passes full expected byte-count and digest checks,
  unchanged file size/mtime, expected write count, compiler, backend, architecture,
  CGO and GOMAXPROCS gates. Sources and binaries match before and after timing.
- Both arms pass three focused test roots, three race repetitions: nine root
  passes each, no failures/skips (default 1.772s, Boring 2.286s package time).
  Known vectors, boundary/partial writes, Sum/reset and same-backend marshal/
  resume are covered. This is not cross-backend persisted-state compatibility
  or a replacement for a cryptographic library's validation suite.
- Initial build failed obtaining VCS status before compilation. The standalone
  diagnostic uses -buildvcs=false equally in both arms and records source hashes;
  this is not a supported-engine build or an engine provenance bypass.
- Initial controller failed after a successful preflight because empty build
  setting values are omitted from JSON. R2 preserves empty values and checks
  the exact Boring compiler suffix, `go1.26.8-X:boringcrypto`. The failed attempt
  remains retained; it is not a discarded timing outlier. Binary sources match.
- Independent read-only review checked gates and the timing/chunk/state limits
  above. No Docker resources or security settings were changed. All jobs ended.

The checkpoint's parent is based on upstream c305ed3757e587045c3c51b5d717f7d64db77377.
This calibration compiles the included standalone program, not that engine.
Its files are byte-identical to measured sources; CSV normalizes CRLF to LF only.
Raw profiles, analyzer, binaries, images and credentials are not published.

## Reproduce

Use Linux/amd64 and **Go 1.26.8** for this host comparison. From this standalone
module, build both arms with the same Go executable, CGO and other flags:

```sh
calibration_outputs="$(mktemp -d /tmp/sha-calibration.XXXXXXXX)"
CGO_ENABLED=1 GOEXPERIMENT= go build -buildvcs=false -mod=readonly -p=2 -o "$calibration_outputs/default" .
CGO_ENABLED=1 GOEXPERIMENT=boringcrypto go build -buildvcs=false -mod=readonly -p=2 -o "$calibration_outputs/boring" .
CGO_ENABLED=1 GOEXPERIMENT= go test -buildvcs=false -race -count=3 -run '^(TestKnownVectors|TestChunksSumAndReset|TestResumeState)$' .
CGO_ENABLED=1 GOEXPERIMENT=boringcrypto go test -buildvcs=false -race -count=3 -run '^(TestKnownVectors|TestChunksSumAndReset|TestResumeState)$' .
```

The default compiler experiment has an
empty GOEXPERIMENT value; it does not disable ordinary Go compiler defaults.
Both binaries take `-input`, `-size`, `-sha256` and optional `-chunk` arguments.
Run them with GOMAXPROCS=2 and GODEBUG empty, in AB/BA order for six pairs. Record
external process wall time as well as each JSON result and retain all samples.
Explicitly separate preflights and wrong-digest negative controls from timing.

Inputs are the complete [prepared standard OCI image](../bench-rust-toolchain-packaging/README.md),
not synthetic buffers or project outputs. Expected full SHA256 values:

- Compressed blob: `12a0a3a340cd71479adee324d1351b8cf305d3d874a9efa82e5dc7d58930d08b`.
- Uncompressed tar: `539af938c66874e323ed86c26658d305b1cc421ee41f46cfb831697b84f9d2ae`.

Local complete controller and receipts: `/tmp/dagger-sha-backend-calibration.BdcQtl8q`.
`bash build.sh` then `python3 calibrate.py --run NEW_CHILD_NAME`; output directories
refuse overwrite. Those local controllers need path adaptation on another
machine; this is not a turnkey public image/download or Rust demo.

Receipt SHA256: summary
`3ae972432e4e41212b4d25c51ebe1bce57273d823b8223ebf4447697896fb2cf`;
raw rows `0f78cc02aac2d82bc1c5777a9a13966f996b844d5f451f7b9899a4bff2ec42b3`.
Default binary `01fd18a4de7109f1ab41a23e03ddbb8f193ee368069d9b9f8707d04a65e600f9`;
Boring binary `cfed226a36d47aff05718786f7a1f0d8ec143e3f55afab6caaed70c2a881631f`.
