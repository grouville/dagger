# Single project import: correct cache reuse, no broad CLI win

This is a **module-only experiment, not a promoted speed fix**. It is stacked on
the [parser-statistics checkpoint](../bench-parser-choice-statistics/README.md).
Both treatments run the same parser-candidate engine and CLI. No engine behavior,
cache key, listener or session lifecycle is changed by this experiment.

## Hypothesis

wcprof identified five distinct host imports: module configuration, implementation,
module `.env`, root project toolchain configuration, and Cargo source. They are not
duplicate requests. In particular `.env` may be gitignored and cannot safely be
replaced by the implementation snapshot.

The candidate reads the required Cargo source once, then derives root
`rust-toolchain` / `rust-toolchain.toml` using `Directory.filter`. That existing
API preserves content hashing, so unchanged toolchain contents can retain
equivalent cache identity after unrelated edits. The identical immutable project
snapshot also feeds Cargo. Source exclusions and `gitignore=false` are unchanged.

The profiled toolchain sequence confirms four Host.directory executions instead
of five. This is not proof of a net latency improvement: filtering and other work
must still be measured.

## Results retained, including losses

Three independent AB/BA/AB pairs, six fresh engine/Cargo states. Three within-run
ordinary edits are summarized before pairing; they are not nine independent pairs.
Positive savings mean the candidate is faster. Milliseconds:

| Flow | Paired CLI saving, median [min, max] | Favorable pairs | Candidate Dagger median | Native median | Paired native overhead median |
| --- | ---: | ---: | ---: | ---: | ---: |
| First check¹ | -1,567.6 [-16,166.9, -116.7] | 0/3 | 18,924.4 | 6,680.3 | +10,572.9 |
| Provision + first check¹ | -1,565.8 [-16,569.3, -128.0] | 0/3 | 19,135.1 | 6,680.3 | +10,783.5 |
| Exact hit | -0.1 [-0.4, +17.6] | 1/3 | 416.5 | 144.9 | +279.8 |
| Application edit | **-41.6 [-44.2, +32.9]** | **1/3** | 840.2 | 285.7 | +550.5 |
| Workspace-library edit | -1.3 [-30.5, +21.1] | 1/3 | 946.3 | 452.7 | +488.3 |
| bstr 1.12.0 → 1.13.0¹ | +8.2 [-67.7, +16.7] | 2/3 | 2,086.8 | 1,626.2 | +488.2 |
| Unchanged after upgrade | +24.5 [+15.5, +54.8] | 3/3 | 410.9 | 123.9 | +288.6 |

¹ Includes wcprof instrumentation. Other timed warm runs omit `--profile`, but
all export OTLP to a local receiver. Native is Cargo through docker exec in the
same pinned preinstalled Rust image. Paired overhead is a median of differences;
it need not equal the two displayed marginal medians' difference. Full points,
ratios, ranges and native-normalized differences are in [summary.json](summary.json).

Every flow still loses to native. Normalizing by native variability does not turn
the application regression into a win: paired overhead worsens by 36.9 ms median.
The cold outlier remains: candidate run 2 takes 33.820 seconds, with a 21.527-second
Rust delivery envelope versus 8.106 seconds for its paired control. That locates
about 13.4 seconds of the extra wall time in image delivery; it does not establish
network/CPU causality or justify excluding the sample.

The later, **post-failure-recovery** application profiles show filtering costs
3.8–4.1 ms and fewer workspace-read calls; exact filter calls are hits around
0.055–0.065 ms. Their Cargo action is 34.6/16.9/7.2 ms slower in B. Those are not
ordinary timed one-crate application profiles and cannot explain that row's
regression by themselves. A general engine-filter rewrite is not justified by
these small filter costs. Next useful diagnostic: ordinary novel edits on one
engine, more alternating pairs, separate full wcprof samples and actual crate gates.

## Correctness and remaining gates

All 36 fullflow wcprof structural/count/execution/byte/package validations pass;
18 cache snapshots parse and all 36 ordinary affected-crate audits agree with
native. The real bstr upgrade selects 1.13.0 and leaves unrelated memchr cached.
Failure, repair, failing-source revisit, cached repair and engine restart remain
in the sequence. Full pinned Rust transfer/read bytes remain 316,873,658.
All six owned container/cache groups were independently verified removed; logs,
workspaces and captures are retained. No existing engine cache was reset.

The separate toolchain sequence has 11/11 complete profiles. Source failure and
repair each execute Cargo, with exits 101 and 0, but execute rustup zero times.
Component additions and legacy configuration changes execute setup; invalid
configuration fails; returning to the known final repaired input executes neither
Cargo nor rustup. Components are inspected from immutable result files, not by
running a proxy that might install a missing component. This is correctness, not
performance evidence.

Before any promotion:

- Restore the public diagnostic `toolchainFiles` getter's narrow read. This
  prototype unnecessarily makes it import all Cargo source, exposing that helper
  to unrelated large/unreadable files. The ordinary check already requires that
  source; the helper does not. The measured prototype is preserved unchanged.
- Add control/candidate parity for gitignored root configs, symlinks (including
  dangling links), zero-byte configs, nested configs and disabled preparation.
  Removing a config tests absence, not an empty file.
- Confirm ordinary-edit latency with stronger same-engine evidence before calling
  this a speed improvement. Neither a removed host call nor correct caching is
  sufficient for that claim.

No artifact export, fmt/Clippy/test-command execution, build.rs/features matrix,
concurrency, macOS or remote performance is validated here. This remains a minimal
check fixture, not the completed official Rust module.

## Reproduce and source pins

Frozen local owner: `/tmp/dagger-rust-single-source.FwiNYoEd`.
Cohort: `/tmp/dagger-rust-single-source-ab-d2k_3qm_`.
Engine parent: `503d3410ef3df63fa6bc7a55c5c2453c4951c2c2`, based on main7c35.
Both image IDs: `sha256:c057d7eed790760d88e4cffb0f540adb9e230823b81759c0e86eeaae49d141a0`.
Both CLI hashes: `23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270`.
Control module SHA256: `f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1`.
Candidate module SHA256: `591d98754a680f4199c807043fdf2fc471cd3139530f75fc80a5f3f1f2b7d1e5`.

Original commands:

```sh
python3 capture-toolchain.py --execute
python3 analyze-toolchain.py
python3 run-fullflow.py --execute
python3 analyze-fullflow.py /tmp/dagger-rust-single-source-ab-d2k_3qm_
python3 summarize-fullflow.py /tmp/dagger-rust-single-source-ab-d2k_3qm_
```

The controllers preserve original source/CLI/image guards, direct-origin registry
configuration and explicit cleanup ownership. They depend on the preceding
checkpoint's included cold-flow adapter/build helper and original local paths;
adapt those paths and pin freshly built binary identities on another machine.
They are not a portable one-command demo. Run heavy work sequentially. Ordinary
CLI invocations create their own sessions; no listen/watch command is required.

Docker, CLI, engine image, local module and native Rust image are preinstalled.
Host page/CDN caches are not purged. Native follows Dagger for the initial check.
This is an engine-cache-cold diagnostic, not complete onboarding or default-route
performance. Separate image-stream/hash/codec experiments are absent; no gains
from those cohorts are added to these results.

Raw fullflow telemetry: 42,175,162 bytes, SHA256
`bdc0f87291b60f7ad6b9d308c9be546f9c289ee0ade54b982dde9e0850b21849`.
Full report SHA256: `04e8b25aa60259ec63b56d81b014b3cd71b83bc28b87f4fd39e2a9c25f9e801d`.
Full summary SHA256: `85261fe6c6f4d63ef69dae5ee39a7f9e2042672c543f88e10c695aedd0317fae`.
Raw toolchain telemetry SHA256:
`65c99be6ac5a641eb1225c82163bcc66616f1c192be98bb9cf56a0d4fd5bfe79`.
Raw captures, private wcprof analyzer and binaries remain local. No PR, OCI upload,
maintainer approval or performance-goal completion is claimed.
