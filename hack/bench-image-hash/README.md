# Experiment: overlap image-layer hashing with extraction

This branch preserves a measured **containerd dependency experiment**, not a
new Dagger unpacker or a shipping dependency replacement. No production Dagger
source or go.mod changes are included. It is based on upstream main
6bf59d50654ce9244ebeee1cc090b7dce3fe3083 (reverified 2026-09-12), which already
uses containerd v2.2.5. No PR has been opened and no maintainer approval is claimed.

See [RESULTS.md](RESULTS.md) for context, source/build pins, every cold sample,
phase attribution, correctness checks, failures, limits and retained local
commands/artifacts. [cold-summary.json](cold-summary.json) records the exact
paired calculations. Maintained private wcprof code/raw telemetry are not
published here; evidence hashes and completeness/replay details are recorded.

## What is worth reviewing

[containerd.patch](containerd.patch) changes only containerd's stock applier.
For descriptors at least 8 MiB it hashes the same ordered uncompressed bytes
on one joined worker, with three reusable 256 KiB buffers. It does not skip
hashing, publish a digest early, change snapshot/cache identity, or add a
snapshotter. The natural upstream path is containerd review/release followed
by a normal Dagger dependency bump. The measured local replace is deliberately
not part of this branch's implementation.

Three profiled fresh-engine pairs on the recorded host favored the candidate:
median paired first-check saving 1.488125 s, unpack saving 1.450171 s. All 30
complete capture/execution gates passed. Cold wcprof replay drift still reached
5.4%, so its what-if numbers are not treated as measurements. A one-CPU local
apply diagnostic slightly regressed (paired median 21.016 ms, about 0.5%).
Remaining candidate cold overhead including provisioning is about 9.66 s;
this is not native parity, complete installation, or a universal speedup.

## Reproduce the source and correctness checks

Use a disposable containerd v2.2.5 checkout, not Go's shared module cache:

```sh
git -C "$CONTAINERD_CHECKOUT" apply --check "$EVIDENCE/containerd.patch"
git -C "$CONTAINERD_CHECKOUT" apply "$EVIDENCE/containerd.patch"
cp "$EVIDENCE/fixtures/pipelined_hash_test.go.txt" \
  "$CONTAINERD_CHECKOUT/core/diff/apply/pipelined_hash_test.go"
cd "$CONTAINERD_CHECKOUT"
go test -race -count=3 -run '^TestPipelinedHash' ./core/diff/apply
```

`EVIDENCE` is this directory; `CONTAINERD_CHECKOUT` is the disposable source.
The expected patched apply.go SHA256 is
d772b58fa595d933f7e89ba3130c76749d52945178608c0d50066d2dcfea73de.
The helper unit fixture is the same one that passed the retained standalone
race runs. Actual filesystem application was additionally tested through the
supported Dagger engine-dev environment, not mocked mounts:

```sh
# In a disposable Dagger checkout with only a temporary local containerd
# replacement under the engine-dev Source allowlist (for example internal/):
cp "$EVIDENCE/fixtures/pipelined_apply_test.go.txt" engine/snapshots/pipelined_apply_test.go
cp "$EVIDENCE/fixtures/pipelined_apply_compressed_test.go.txt" engine/snapshots/pipelined_apply_compressed_test.go
dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 api call engine-dev test \
  --pkg=./engine/snapshots --run='^TestPipelinedApply' \
  --race=true --count=3 --parallel=1 --timeout=90s --test-verbose=true
```

The recorded supported runs were separate: the initial suite reported 45
passing results; the later compressed-failure suite reported 33. The combined
command above is a reproduction instruction, not a claim of an already-run
combined suite. Fixtures are inert .go.txt files here so this evidence-only
branch cannot accidentally change ordinary engine builds or tests.

The local full-CLI controllers in RESULTS.md pin the full experimental Dagger
stack, CLI, module, native workload and fresh-store ownership. They are retained
host-specific evidence, not an assertion that this small branch alone installs
that stack or reproduces the full demo on a clean machine. Completing portable
end-to-end packaging remains part of the broader Rust-module goal.
