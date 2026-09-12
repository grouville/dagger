# Zstd plus stream/hash: cold mechanism win, mixed full-flow result

This is one cohort with three independent AB/BA/AB engine pairs. Both sides use
the **same normal-Dagger-exported Zstd image**, CLI and module. A is the reviewed
baseline engine; B is the previously built corrected stream/hash experiment.
This measures composition, not the sum of older gzip, hash and streaming scores.
There is no new production patch in this follow-up. See [ZSTD_VALIDATION.md](ZSTD_VALIDATION.md)
for the added standard-decoder correctness gates.

## Measured cold result

Times are seconds; positive savings favor B. Every measured pair is retained.

| Pair/order | A first check | B first check | Saving | A image delivery | B image delivery | Saving |
|---|---:|---:|---:|---:|---:|---:|
| 0 AB | 12.654474 | 11.128796 | 1.525677 | 4.375189 | 3.363863 | 1.011326 |
| 1 BA | 12.156330 | 11.823460 | 0.332870 | 4.285431 | 3.351578 | 0.933852 |
| 2 AB | 12.134935 | 12.605645 | -0.470710 | 4.236643 | 3.369246 | 0.867397 |

The shared image-delivery envelope improves in 3/3 pairs: **0.933852 s median**,
range 0.867397–1.011326 s. All B traces contain the largest layer's private-stream
span and compressed reads before that layer's own download finishes. All A traces
use the eager path. Both sides download and unpack the exact same **294,925,737
compressed bytes**. These checks establish the intended mechanism, not just a
faster run with missing work.

Full CLI first-check improvement is smaller and mixed: **0.332870 s paired
median**, 2/3 favorable, range -0.470710–1.525677 s. Provisioning-plus-check saves
0.306366 s median, range -0.460265–1.516232 s. The median paired reduction in
provision-inclusive overhead relative to each run's own native reference is
0.357102 s, favorable in 3/3 pairs. Native reference variability is retained.

Candidate first-check median is 11.823460 s, range 11.128796–12.605645 s;
provisioning-plus-check median is 12.085220 s, range 11.375400–12.836585 s.
Per-run provision-inclusive native overheads are **3.976422, 5.689006 and
5.621413 s** (median 5.621413 s). Corresponding native references are 7.398977,
6.396214 and 7.215172 s. These are nowhere near the 0.5–1 s onboarding target.
Do not subtract unrelated marginal medians or add gains from other cohorts.

Why the full-flow improvement is smaller: cold Cargo process time inside B loses
269.175 ms at the paired median (two losses and one gain), and the final B sample
has a 1.504 s connection span versus A's 0.483 s. Its Control/Info call accounts
for about 1.08 s. These observations locate delays; they do not prove their
underlying cause or authorize removing the losing sample. The separately parked
socket-readiness candidate was **not** included here.

## Warm regressions remain visible

Within-run repeated samples are summarized before pairing engines; three warm
repeats are not nine independent pairs. Positive savings favor B.

| Flow | Paired CLI saving, ms | Range, ms | Favorable pairs | B median, ms | Median per-run native overhead, ms |
|---|---:|---:|---:|---:|---:|
| Unchanged | 0.743 | -34.373–10.880 | 2/3 | 441.773 | 299.151 |
| Application edit | -24.650 | -58.892–-8.040 | 0/3 | 848.558 | 562.255 |
| Workspace-library edit | -10.850 | -41.421–-8.251 | 0/3 | 1020.833 | 569.185 |
| bstr 1.12.0 → 1.13.0 | -83.465 | -135.488–18.964 | 1/3 | 2210.892 | 631.982 |
| Unchanged after upgrade | 44.927 | -14.799–46.283 | 2/3 | 433.597 | 318.082 |

Application native overhead worsens 29.927 ms at the paired median (3/3 losses),
library overhead 39.585 ms (2/3 losses), and upgrade overhead 96.906 ms (2/3
losses). Their causes are not established. Image decoding does not run on these
warm hits, so image-path savings are not a warm-speedup explanation. **Every
representative flow remains slower than native.** This combined stack is not
promoted as the winning default; generic session/module/source overhead and the
edit regressions still need investigation.

## Scope and trustworthy profiling

Ordinary standalone `dagger check rust:check`, no listener or resident CLI.
Six fresh engine/Cargo stores; same ripgrep revision, actual external library
upgrade, root toolchain config, flags and module. Docker, CLI, engine/native
images and local module are already installed. Both treatments fetch from the
same prepopulated, task-owned loopback-only unauthenticated registry. Host page
and CDN caches were not purged. Native uses `docker exec` in the matched Rust
image, and follows Dagger for the initial check. This is not public-registry
delivery, complete installation, bare-host Cargo, macOS or remote performance.
No artifacts, fmt, clippy or test-command performance is claimed.

Cold checks and external upgrades are profiled; the other timed warm operations
are not. Post-timer diagnostics have separate captures, including a later app
edit after failure/revisit/cached repair, which rebuilds three crates. The actual
ordinary timed app edits rebuild only ripgrep; ordinary library edits rebuild
grep-printer/grep/ripgrep. These histories must not be conflated.

All **36 wcprof, 18 cache and 36 ordinary warm-crate audits pass**, along with
both final-pair component transition sequences. No rejected runtime samples.
Every capture passes structural completeness/count and expected execution checks;
replay drift is -0.0% to -0.1%, including cold runs. Exact and restart hits perform
no Cargo execution. Full compressed-byte, checksum/progress, dependency-version,
failure/repair/revisit, retained-result and restart-cache gates remain enabled.

Do not equate B's metadata-only `preparing pull` with A's complete `pulling`
span. The common delivery envelope includes all preparation/download/unpack.
Streaming unpack includes input waits, while HTTP reads can include consumer
backpressure: a long HTTP span is not proof of a network-bandwidth bottleneck.
wcprof what-if savings remain hypotheses; phase medians are not additive CPU.
Hashing and streaming were a combined treatment, not independently estimated.

The frozen inherited `phase-summary.py` assumed both sides had a `pulling` span.
Read-only review caught this before use. A separate `phase-summary-v2.py` keeps
the real names, compares only shared envelopes and adds explicit mechanism gates.
`summarize-v2.py` corrects same-image/one-cohort labels without changing timing
math. Original scripts/captures remain intact. One premature offline summary
attempt ran before report.json existed; its FileNotFoundError log is retained,
then the same summarizer passed after analyzer completion. No runtime rerun,
sample substitution or changed measurement gate resulted.

## Reproduction and exact evidence

One-shot local controllers, frozen to the recorded inputs:

```sh
python3 /tmp/dagger-zstd-stream-ab.sZvk4EQI/run-pairs.py --execute
python3 /tmp/dagger-zstd-stream-ab.sZvk4EQI/analyze.py /tmp/dagger-rust-zstd-stream-ab-rfugl8dy
python3 /tmp/dagger-zstd-stream-ab.sZvk4EQI/summarize-v2.py /tmp/dagger-rust-zstd-stream-ab-rfugl8dy
python3 /tmp/dagger-zstd-stream-ab.sZvk4EQI/phase-summary-v2.py /tmp/dagger-rust-zstd-stream-ab-rfugl8dy
```

Use new owned roots/identities for a repeat; these controllers refuse to overwrite
evidence. Heavy work was sequential. All six temporary runtime/cache groups and
the registry/network/volume were independently verified absent after completion;
the receiver stopped. Retained dev engines were not replaced. Public image
upload is not part of this work. The compact published JSON preserves every
timing and validation result; raw telemetry and the private analyzer remain local.

| Input / artifact | SHA256 or immutable ID |
|---|---|
| Upstream main, rechecked | 6bf59d50654ce9244ebeee1cc090b7dce3fe3083 |
| A engine | 3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181 |
| B engine | 848627df950f9d0211436e3210bbbf34ba97f7a1823a528880c5dace238d9a2c |
| CLI | 98fc6ea8e60fc574117300dce9334d008ee4317ee35bce5a8eebe03455110d3a |
| Zstd image manifest, both sides | a19403dcd51e5c82c3f694cea215de799c12929cd0d5536a21c6333489ead534 |
| Module main.dang | f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1 |
| run-pairs.py | c61f7827737813c8be27cbe439792b07be275987716a86831d3acc33a1d7126b |
| run-local-codec-check.py | 3fd6b9bbb32e0bba2ec9e4b50e969b99f834766d46bd4c29e229c24be898d77c |
| analyze.py | 6d48d7be87f2befc94291a06e044349a7a4ac893eb30d671a6459e1172ca7761 |
| summarize-v2.py | 60b243c53ac5086f72efbfe2fc0e397bfdd73242a1adf6acc8d6dd7f94ceb576 |
| phase-summary-v2.py | 20d79187207c47878a608d850c878d443c72625f09d55875a177d3a230e36399 |
| cohort.json | 4af1a63078922524228a84b2d0888f0d6340727bd0fc21329e1c808f97e77e17 |
| analysis/report.json | 14bccc110748ccf8b338b7bf319658551e636c702629f662fd8634510517c1f8 |
| Full local summary.json | 18e1ab92c86ab9a3fe2bb0a2b73a96481d5fa4292f823eac9ed3c471b69bef95 |
| phases-v2.json | 9b8ee6cfcaead5b48f1c5fce773fbcfa569104d9a92df5c70dc3fd850feebe5f |
| Raw telemetry, 46,140,332 bytes | fd260cc0990e95c8297174e82583e3463c72e44ad0f05e5abeebd37cb53d4878 |

Image production/byte-equivalence recipe is published separately on
`experiment/rust-zstd-toolchain` at 84d985d31267495efba36da949e830540dcf690e.
The full experimental engine/module source parent remains db9d005c715ac9d146780d783faf7f7b55d23e5e
atop the stated main, not a claim that this evidence-only branch alone installs
that stack. See [zstd-comparison.json](zstd-comparison.json),
[zstd-phases.json](zstd-phases.json) and [zstd-profile-validation.json](zstd-profile-validation.json).
