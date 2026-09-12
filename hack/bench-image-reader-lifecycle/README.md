# Containerd progress-reader shutdown experiment

This is an independently reviewable dependency fix and regression evidence,
based on Dagger main6bf59d50654ce9244ebeee1cc090b7dce3fe3083. It does not change
Dagger's production source or install a local dependency replacement. No PR,
maintainer approval or production-readiness claim is implied.

## Context and fix

The Rust cold-start experiment overlaps full image downloading and extraction.
A real10MiB compressed-layer integrity failure exposed a data race between
containerd progressReader.Close and the external decoder's input readCounter.
The reader code was unchanged from containerd v2.2.5. A focused race test with
the stock applier reproduced the same defect independently of streaming or the
experimental hashing worker.

The patch protects the progress count and callbacks, closes the source once,
preserves its error for concurrent closers, and prevents callbacks after final
Close. It does not hold a mutex across borrowed Read or source Close. Deferred
unlocking preserves cleanup if a progress callback panics. Callbacks must not
re-enter this reader; this is not a general concurrent-reader implementation.

Scope matters: an already admitted borrowed read can finish after Close and
its bytes need not appear in terminal error-path progress. This patch does not
promise a generic decoder-process join or make arbitrary inputs interruptible.
The owned private pipe requires its own interruption/read fence in the separate
streaming experiment. Normal successful EOF still reports the complete count.

The natural delivery path is containerd review/release, then an ordinary Dagger
dependency update. No new snapshotter, cache identity or egraph policy is needed.

## Reproduce

Use a fresh disposable containerd v2.2.5 checkout, never Go's shared module cache.
`EVIDENCE` is this directory; `CONTAINERD_CHECKOUT` is that disposable checkout.

```sh
cp "$EVIDENCE/fixtures/progress_reader_test.go.txt" \
  "$CONTAINERD_CHECKOUT/core/diff/apply/progress_reader_test.go"
cd "$CONTAINERD_CHECKOUT"
# Expected failure on stock: same counter race and callbacks after Close.
go test -race -count=1 \
  -run '^TestProgressReader(CloseIsTerminal|ConcurrentClose|CloseDoesNotJoinBorrowedRead)$' \
  ./core/diff/apply

git apply --check "$EVIDENCE/containerd.patch"
git apply "$EVIDENCE/containerd.patch"
# Expected pass, including concurrent close errors and callback-panic cleanup.
go test -race -count=10 -run '^TestProgressReader' ./core/diff/apply
```

Patched stock apply.go SHA256:
`f512acae95445fcc1f9b1fe6d204a5a0c82ee13e865f7bb1668bc70bab4bfd43`.
The fixture is inert here so ordinary Dagger builds/tests are unaffected.

## Validation and performance limits

On Linux/amd64 with Go1.26.8, the stock3-test subset failed with the original
race. All final5tests passed10race repetitions using the progress-only patch
against stock apply.go through a read-only Go overlay. The Dagger module graph
pinned dependencies; this is not a full stock-engine reproduction. Tests cover
terminal/idempotent progress, concurrent reads/close, a non-interruptible borrowed
read, concurrent close errors, and callback-panic cleanup. The initial mutex
prototype failed the panic test; that failure is retained, not hidden.

Retained local evidence: `/tmp/dagger-stream-reader-lifecycle.w7gTjM09`.

- Stock failure `reader-stock.log`: SHA256
  5f265cb333f4566eb7ce6bf889bfc5dfb620e4546853563ed380a20d8a22edd1.
- Final stock-plus-fix `reader-stock-fixed.log`: SHA256
  06699b211cea45d7ba933e12a14144b28d725d85dd3bf3a0eba51d8b2a7c71ec.
- Generated patch SHA256:
  17fd11e2f56e47863ee37e1f7efc7601915ae7ff1c40908af2e67b28f2141d80.

No standalone speedup has been measured for synchronization. It enables further
correctness testing of the larger image-stream experiment, whose corrected
combined candidate saved2.276721s paired median in3fresh-engine comparisons.
That combined result is not attributable to this reader patch alone; it still
has7.549737s median overhead versus native including engine provisioning, and
slight warm regressions. Full cold data and remaining limits belong to the
stacked verified-image-download-overlap experiment, not this small fix.
