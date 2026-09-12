# Standard Zstd image with verified download/extraction overlap

This follow-up tests the already-published stream/hash engine against the exact
image produced by Dagger's normal `forcedCompression: Zstd` exporter. It adds
no production code, decoder override or lazy snapshotter. The source-built
correctness runner and retained candidate have identical production content;
only three test files differ. The comparison is experimental, not a shipping
Rust module or an installation-from-nothing result.

## Correctness reproduction

First prepare the disposable source and containerd dependency described in
[README.md](README.md), including `engine.patch`, the combined containerd patch
and fixtures. Then apply the additional test patch:

```sh
git apply --check hack/bench-image-stream/zstd-tests.patch
git apply hack/bench-image-stream/zstd-tests.patch
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call engine-dev test \
  --pkg=./core/integration --run='^TestEngine$/^TestVerifiedStreamZstdRace$' \
  --parallel=1 --timeout=5m --count=1 --test-verbose=true
```

The supported runner compiles the actual resolver source with race detection,
then runs its real mounted-snapshot tests three times. The standard Zstd decoder
is unchanged. Both 2 MiB and 10 MiB incompressible payloads cover successful
import, wrong compressed digest, truncated transfer, wrong uncompressed digest,
source-label failure, caller cancellation and a corrupted Zstd checksum. The
large input crosses the hash worker's 8 MiB compressed-descriptor threshold.
Checksum corruption is included in the descriptor actually served, so that
case checks frame verification independently from transport verification.

The shared fixture preserves actual mounted-marker observation while the rest
of the compressed input is blocked, no early content/result publication,
private snapshot ownership, result retention and reclamation after lease release.
The supported race run passed without a production change. This is focused
correctness evidence, not broad concurrency or macOS/remote validation.

The separate early-invalid-tar fixture also passed with its caller still live.
Its limit matters: it does **not** deterministically observe a decoder read
blocked at the instant of extraction failure. A source-review concern about
decoder/input close ordering remains unproven, not a fixed or exhaustively
covered bug. No speculative production patch was added.

## Exact local test evidence

Owner: `/tmp/dagger-stream-zstd-validation.QlVwqMfp`. Both single-use stages
record the full source file hashes before and after the source-built tests.
An independent directory comparison found only the three test-file differences
from `/tmp/dagger-stream-reader-lifecycle.w7gTjM09/engine-source`.

| Artifact | SHA256 |
|---|---|
| early-error-before/stage.json | 762ef1a04babcc528319d00abd4788857677ad3e4fbebaa76979f3745d9bce89 |
| early-error-before/engine-dev.log | 5f24f73d4005e2eb3aa72f092870e9cf2c7d3a5d8c59b5ea56bf68f7f9cb2632 |
| zstd-race/stage.json | ed9824bedd973847638a3fb72e896439248e4cffc1fa0b6c3587de63adec196d |
| zstd-race/engine-dev.log | 866cb7dcfa8453e791473f59426a4a0e8fedc33590be2cf27063730f3f74266b |

Stage commands:

```sh
python3 /tmp/dagger-stream-zstd-validation.QlVwqMfp/run-stage.py early-error-before \
  '^TestEngine$/^TestVerifiedStreamZstdEarlyError$'
python3 /tmp/dagger-stream-zstd-validation.QlVwqMfp/run-stage.py zstd-race \
  '^TestEngine$/^TestVerifiedStreamZstdRace$'
```

These commands document the recorded runs; the controller refuses to overwrite
their existing directories. Create a fresh owned stage for a repeat. TUI logs
retain local-remote/as-sdk migration warnings and nested-service teardown ERROR
entries despite successful test assertions. They are not wcprof latency captures.
