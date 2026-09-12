# Pipelined image hashing: supported tests and full cold comparison

Status: a measured experimental improvement, not a shipping Dagger dependency
change. The Rust performance goal remains unmet. No lazy snapshotter is used.

## Context and change

The prior cold CPU diagnostic found approximately 2.10 CPU-seconds of SHA256
inside containerd's layer applier on this i5-9300H host (no SHA instructions).
The candidate overlaps ordered uncompressed-tar hashing with extraction. It
uses three reusable 256 KiB buffers, copies incoming bytes before returning
from Write, drains/joins the worker before digest return and on errors, and
retains the normal stock applier and digest computation. Eligible descriptor
size is at least 8 MiB, including uncompressed descriptors.

Candidate source is containerd v2.2.5, combined apply.go SHA256
`d772b58fa595d933f7e89ba3130c76749d52945178608c0d50066d2dcfea73de`.
Local layer evidence, source, helper tests and byte/metadata inventory are in
`/tmp/dagger-rust-unpack-profile.E48gnw6v/README.md`. The earlier isolated
1.085146 s paired saving is not added to the full-CLI result below.

## Supported correctness and build

The scratch source is `repo/`, base db9d005c715ac9d146780d783faf7f7b55d23e5e,
an experimental stack rebased onto upstream main 6bf59d50654ce9244ebeee1cc090b7dce3fe3083.
The one dependency is temporarily replaced by an owned extracted source under
`internal/bench-pipelined-image-hash/dependencies/`. This local replace and
vendored experiment are not proposed shipping changes. Intended delivery is
upstream containerd review/release followed by a normal Dagger dependency bump.

Supported engine-dev test passed:

```text
engine-dev test --pkg=./engine/snapshots --run=^TestPipelinedApply
  --race=true --count=3 --parallel=1 --timeout=90s --test-verbose=true
```

All 45 reported test results passed. Tests cover raw threshold boundaries,
raw/gzip/zstd large payloads, trailing decoded data in digest/size, exact file
hash/mode/time, xattr, symlink and hardlink identity, malformed/truncated tar,
gzip CRC failure, raw read errors and cancellation, worker joins, and four
independent concurrent applies. Test source SHA256:
`213bcedfa58037ed77eb8e28256ae6c4997861d9d2619196c88c935451a390c5`.

`attempt-2/supported-tests.log` retains the supported run. Standard engine-dev
deployment and a query using the fixed baseline CLI then passed; build manifest
is `attempt-2/engine-build.json`, SHA256
`e7620ec9d0f55428ceef8e0675a51dc3fc584c75013d44955d171ff192aeec6c`.
Baseline image: `sha256:3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181`.
Candidate image: `sha256:3b711dbd1020dc827a3a1e452fba01c480e924cdf6151b623f8214ca5a1abf5d`.
Only the fixed baseline CLI is compared, SHA256
`984c0d2e5e3f22ffb71bf8a9367b4b784120681ebc27923296adbba9817ac227`.

Failures remain recorded, not omitted:

- Direct host tests could not mount in this user namespace/read-only mount
  location. That early cleanup also exposed a progressReader counter race;
  baseline attribution has not been tested. See `real-applier-local.log`.
- The first supported build failed before tests because engine-dev Source
  excludes dependency source placed under hack/. Moving the temporary
  dependency under the already-supported internal/ tree fixed the wiring.
  Source-filter behavior was not modified. The unused hack/ copy is retained.
- Earlier CPU-capture startup and module-cache-overlay failures remain in the
  previous diagnostic; neither became a discarded timing sample here.

## Full cold paired result

Run controller: `run-hash-pairs.py --execute`, same direct-origin registry
configuration, pinned CLI/module/Rust image/project toolchain/native workflow.
Three pairs in AB/BA/AB order, fresh engine volume, CLI state and Cargo cache
namespaces per sample. No parallel heavy jobs. Complete CLI process timing.
This is a profiled engine-cold first check, not complete installation: Docker,
CLI, engine image, local module and native Rust image are preinstalled.
CDN and host page caches are not purged. Network/compiler variation is retained.

| Pair | A first check (s) | B first check (s) | A minus B (s) |
| --- | ---: | ---: | ---: |
| AB | 17.793261 | 16.305136 | 1.488125 |
| BA | 19.188612 | 16.030805 | 3.157807 |
| AB | 17.270753 | 15.996547 | 1.274206 |

- First-check marginal medians: 17.793261 -> 16.030805 s.
- Median paired first-check saving: 1.488125 s, range 1.274206–3.157807, 3/3 favorable.
- Provision plus first-check marginal medians: 17.999947 -> 16.242647 s.
- Median paired provision-plus-check saving: 1.418885 s.
- Median paired reduction in check overhead vs each run's native timing:
  1.304336 s; including provisioning, 1.266763 s.
- Candidate native median: 6.716722 s. Candidate overhead median is
  9.453588 s for first check, 9.658940 s including provisioning. These are
  medians of per-run differences, not differences of marginal medians.
- Unpack span marginal medians: 4.598898 -> 3.248790 s; paired median saving
  1.450171 s, range 1.194385–1.687199, 3/3 favorable.
- Large-layer download interval paired saving: only 0.108986 s, range
  -0.025717–0.143336. Cargo process paired saving: -0.192300 s, range
  -0.253998–0.816697. The large second full-CLI gain includes compiler/runtime
  variation and must not all be attributed to hashing.

The previous independent route experiment saved 8.802786 s paired. Do not add
that cohort's gain to this one and present the sum as a measured single cohort
or as a comparison to the historical 35 s scorecard.

## wcprof and workflow gates

Cohort: `/tmp/dagger-rust-cold-image-ab-5pdsamk4`.
Run the unchanged offline analyzer once on a new cohort (it intentionally
refuses to overwrite its analysis directory):

```text
python3 /tmp/dagger-image-pipeline-source.MfcHBbgL/analyze-cold-ab.py COHORT
```

All 30 complete captures/count/actual-execution/progress gates passed, with no
rejected runs; native package parity, application/library edits, intentional
failure/repair/revisit, and restart exact reuse passed. Both sides transferred
the same 316873658 compressed Rust-image bytes. No changes to selected compiler,
requested rustfmt, flags or normal standalone CLI lifecycle.

Structural completeness is not an exact simulation: cold wcprof replay drift
was -4.5% to -5.4%; warm profiles -0.0% to -0.1%. Treat what-if values as
hypotheses, not measured savings. Full process wall and actual spans above are
the measurements. All 18 retained post-timer cache analyses succeeded.

Raw corpus `hash-pairs-telemetry.jsonl` SHA256:
`cc929983044c4dbe1c78547fc24070c5782db402b5838ee24fa01b3a94b0d7ae`.
Full report `COHORT/analysis/report.json` SHA256:
`7ddcb647cc85fcefcff6db21a4f7dbc3242edbb45076dd953a59d8c2929c410d`.
`hash-pairs-summary.json` records all samples, paired differences and phase data.
The maintained analyzer hash remains de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba.

## Compressed cleanup and one-CPU followup

The additional supported test run, `run-compressed-followup.py --execute`,
passed all 33 reported results with race detection and three repetitions.
Gzip and zstd are interrupted after full/partial input-buffer boundaries by
injected read errors and cancellation. Extraction must have started, no success
descriptor may escape, cleanup is bounded, and hash workers must be joined.
Progress reporting stays enabled. Production source was unchanged from the
full cold A/B; only an additional test fixture was introduced.

New test `repo/engine/snapshots/pipelined_apply_compressed_test.go` SHA256:
`faae7b7d06db9678401b6e9e7d7a19e02147e473c84818c184df77ed216d90da`.
Followup log `compressed-followup/tests.log` SHA256:
`8b630b3a2cee36139917bd8d52e5b722a060ecac9d531f05f0a2e019cba199f7`.
The earlier supported 45-case run and this 33-case run are distinct, not a
single combined suite result.

`run-singlecpu-probe.py --execute` then ran the same frozen standalone applier
binaries and pinned large layer in six sequential network-disabled disposable
containers, `--cpuset-cpus=0`, `GOMAXPROCS=1`, AB/BA/AB. All output inventory and
digest/size checks passed. This is a cached-input applier diagnostic, not a
one-CPU full-engine result; input preverification is outside the timer and
host page caches are not purged.

| Pair | A apply (s) | B apply (s) | A minus B (s) |
| --- | ---: | ---: | ---: |
| AB | 4.099862 | 4.077528 | 0.022334 |
| BA | 4.070605 | 4.091621 | -0.021016 |
| AB | 4.056519 | 4.080687 | -0.024168 |

Median paired saving is **-0.021016 s**, approximately a 0.5% regression, with
one of three pairs favorable. Marginal medians 4.070605 -> 4.080687 s. This
non-win is retained; no claim that every CPU configuration improves. A
single-CPU dispatch policy and hardware-SHA/concurrent-load measurements are
possible followups, not changes included in the measured candidate.
One-CPU result `singlecpu-probe/results.json` SHA256:
`d98f6fe610a2629c007e6753463bddf30ef570687f4553b42f523b9d87777499`.
Both followup sessions (60381, 57676) ended exit 0. All six owned one-CPU
containers were removed and absence verified by the controller.

## Remaining limits and next work

Compressed early-cancellation/read-error tests now pass; one-CPU local
performance is a small non-win as recorded above. No full-engine one-CPU or
performance-under-concurrency validation. The actual
3061-entry Rust-layer inventory did not test xattrs/hardlink topology; synthetic
real-applier tests now do. No macOS/remote-engine/artifact/fmt/clippy/test-suite
or external-dependency-upgrade performance claims from this cold cohort.
No maintainer approval or production-readiness claim; no upstream dependency
release. The experiment's patch and evidence are published on the Dagger fork;
that does not install or ship the temporary dependency replacement.

Current cold B delivery still takes about 7.1 s: pull 3.83–3.90 s followed by
unpack 3.15–3.28 s. On this route the 288.6 MB layer alone transfers in
3.48–3.55 s. Moving this pipeline below 1 s requires fewer bytes, more effective
overlap/throughput, or legitimate already-owned reusable content. Bookkeeping
optimizations alone cannot erase that cost.

Evidence-backed subsequent experiments, all unimplemented here:

1. Reuse already-verified canonical manifest metadata in Pull when only layers
   are absent; B5 repeats HEAD401/tokenPOST/HEAD200 (about 338 ms observed).
   Keep auth request/session scoped and ordinary content leases/verification.
2. Start already-downloaded, verified preceding layers earlier: their unpack
   interval is about 0.47–0.59 s while the large layer is still downloading.
   Full within-blob overlap is a separate larger experiment with earlier failed
   real-snapshot fixtures, not a proven improvement or a lazy snapshotter.
3. Package requested components/source-sync tools in reproducible normal OCI
   images; account for all added bytes/unpack. Current dpkg is only 0.19 s and
   rustup 0.69 s, not the historical multi-second apt installation. Native also
   installs the requested rustfmt, so deleting that requirement is not fair.

Controller session 10923 and analyzer session 8212 are terminal exit 0. Receiver
was stopped by the controller. All six disposable engine stores were removed
by the ownership-checked harness; logs and sources remain. The owned candidate
dev engine is retained, not used as a prewarmed cold store. User workspaces and
existing engines were not reset. One bounded read-only helper completed; no
expanded multi-agent work or other heavy runtime job is active.
