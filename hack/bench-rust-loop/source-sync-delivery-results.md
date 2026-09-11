# Pinned source-sync tool delivery, 2026-09-10

## Finding and decision

Delivering rsync as two checksum-verified Debian packages removes about 2.5s
of first-use setup in this fixture. It does not require a new engine API,
resident worker, host execution, or different Cargo/source-sync behavior.
However, a 30-pair comparison shows a small warm regression. Keep this an
**opt-in packaging experiment**, not the production module default.

This separates dependency resolution (performed when maintaining the module's
tool pins) from delivering/installing those exact tools (still inside the
user's first command). It does not move user-specific Cargo resolution or
compilation out of the timer. The long-term choice between pinned files and a
prepared toolchain image remains open.

## Implementation and trust boundary

The `--pinned-source-sync` fixture setting replaces runtime `apt-get update`
and dependency resolution with ordinary `http(..., checksum: ...)` File inputs,
mounted into the same Rust image and installed with `dpkg -i`. The original
APT path remains the default. The harness rejects other base-image digests
for this experiment, and the action checks the Debian architecture.

APT in the pinned base, using its authenticated official repository indexes,
resolved exactly two missing packages, with no upgrades required:

| Package | Version | Download bytes | SHA256 |
| --- | --- | ---: | --- |
| libpopt0 | 1.19+dfsg-1, amd64 | 43268 | 6f94b488255acd996254f775c77ff3956557c61f860a3c9caeaf65457554194f |
| rsync | 3.2.7-1+deb12u6, amd64 | 424700 | ce99de6b36cbb62dc614a73463e467f2c1ef509545a9a2b33cab19b50530b672 |

These are Debian's existing binaries, not a new synchronizer implementation.
Dagger verifies their digests before installation; dpkg still checks package
dependencies and performs normal installation. There is no trust in an
unverified host binary or a mutable unpinned tool URL. The source reconciler
remains `rsync -rclp --delete`, immediately followed by the same locked Cargo
command in one execution with the same LOCKED source/target caches.

Normal Dagger HTTPState/File/snapshot ownership, content identity, persistence,
and GC apply. No state is stored outside those existing abstractions. The
experiment deliberately does not modify that engine behavior.

This packaging selection is only validated for the pinned Debian bookworm
Linux/amd64 Rust base. It is not an arm64, macOS, musl, custom-image, or arbitrary
toolchain default. Production needs supported-platform manifests, automated
pin/security maintenance, stable artifact availability, and check-tool/native
dependency delivery. Repository pool URLs can eventually disappear even though
their expected bytes are pinned. An OCI toolchain release is an alternative.

## Reproduction and controls

Engine/CLI provenance is in [the CLI startup report](cli-startup-width-results.md).
The engine image is unchanged from 0628f6d5 on upstream f4e83a525; the candidate
CLI includes the go-runewidth update. Module source SHA256 during all four
cold trials: 7fc519a22d9be30c980b351379b0fd443757dbab1d50b1810f99bfd4a7bd5a93.
The module experiment was uncommitted on parent f48f4414be during measurement;
metadata records its tracked diff hash. No engine rebuild was needed for this
module-only experiment.

Start the local OTel receiver according to the telemetry-capture skill, then:

```sh
env -u DAGGER_CONFIG -u DAGGER_CLOUD_TOKEN -u DAGGER_CLOUD_URL \
  -u DAGGER_SESSION_PORT -u DAGGER_SESSION_TOKEN \
  -u OTEL_EXPORTER_OTLP_HEADERS -u OTEL_EXPORTER_OTLP_TRACES_ENDPOINT \
  -u CPUPROFILE DO_NOT_TRACK=1 \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:43181 \
  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:43181/v1/logs \
  OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:43181/v1/metrics \
  OTEL_EXPORTER_OTLP_TRACES_LIVE=1 \
  python3 hack/bench-rust-loop/run.py \
    --dagger /tmp/dagger-rust-cli-width-after \
    --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
    --ripgrep /tmp/dagger-rust-ripgrep-reference --samples 3 \
    --fresh-engine localhost/dagger-engine.rust-perf-f4e83a525 \
    --dependency-upgrade --pinned-source-sync
```

Omit `--pinned-source-sync` for the APT control. Add `--profile-first` only for
the native-profile diagnostic pair. Trial order was pinned-profiled,
APT-profiled, APT-repeat, pinned-repeat. The external-dependency order within
those trials was respectively native-first, Dagger-first, native-first,
Dagger-first. No shell phase probes were used.

Each trial starts an empty engine volume and fresh CLI XDG state, then runs
ordinary standalone checks, with unique Cargo cache namespaces. Package and
Rust image downloads, unpacking and installation stay inside the first check.
No resident CLI/listen process is used. The reset loop removes only that
trial's engine, engine volume and native container; logs and source copies
remain. Existing development engines and their caches are untouched.

These are **engine-cache-cold** checks, not complete new-user installation:
Docker, CLI, engine image, local module and native-control Rust image already
exist. Docker's image store, OS page cache, registries/CDNs and network conditions
are not reset. Native is Cargo via docker exec, with the same toolchain,
workspace, flags and dependency histories. Analytics is disabled and local
OTel enabled throughout; the default report frontend is used by this runner.

## Cold observations

| Trial | Provision through first check, s | CLI first check, s | Native first check, s |
| --- | ---: | ---: | ---: |
| Pinned, native-profile diagnostic | 22.29 | 22.09 | 6.64 |
| APT, native-profile diagnostic | 26.54 | 26.33 | 5.85 |
| APT repeat, native profiling off | 31.95 | 31.74 | 6.36 |
| Pinned repeat, native profiling off | 24.10 | 23.89 | 6.00 |

Only one trial per variant in each profiling condition: these are observations,
not a statistically established cold speedup distribution. The 4.25s and
7.85s whole-flow differences must not all be attributed to tool packaging.
wcprof ranks HTTP work at 9.59s versus 8.27s in the diagnostic pair, and 14.59s
versus 10.00s in the repeat. Image unpacking stays around 4.5-4.7s; Cargo time
also varies. These rankings are counterfactual estimates, not additive phases.

The directly observed execution envelopes isolate a smaller, repeatable gain:

| Boundary, ms | APT diagnostic | Pinned diagnostic | APT repeat | Pinned repeat |
| --- | ---: | ---: | ---: | ---: |
| Install execution | 2758.89 | 215.12 | 2915.10 | 214.70 |
| libpopt HTTP fetch | included in APT | 75.79 | included in APT | 66.25 |
| rsync HTTP fetch | included in APT | 82.80 | included in APT | 87.91 |
| rsync + Cargo execution | 6505.01 | 6137.86 | 6690.94 | 6014.04 |

The two HTTP fetches can overlap; do not blindly sum them. Execution envelopes
include runtime startup/finalization as documented in the source-sync report.
The installation reduction is roughly 2.54-2.70s before accounting for the
separate small downloads, not a demonstrated 8s module optimization.

## Warm and invalidation checks

All four runs passed source-edit checks, deliberate failure (exit 101), repair,
revisiting the earlier failing source (101 again), and repair (0). Each bstr
1.12.0 -> 1.13.0 upgrade rebuilt the same 10-package set on both sides, retained
memchr, and left locked inputs unchanged. All per-scenario samples, outliers
and first-use values are in [the timing CSV](source-sync-delivery-timings.csv).

The repeat's three-sample warm Dagger medians regressed: exact 414.37 -> 487.28ms,
application edit 782.67 -> 857.61ms, workspace-library edit 992.51 -> 1036.90ms.
The corresponding earlier trials favored the candidate. Do not use either
unpaired warm batch to claim a causal improvement or regression magnitude.

A separate **30-pair alternating exact-check comparison** used the same CLI,
same existing engine, shared isolated CLI state, and source-identical prepared
workspaces. `diff -rq` found no source differences after excluding Dagger
configuration/lock files and .git. Tool-delivery settings and independent Cargo
cache namespaces differ. One warmup pair is retained but excluded from stats.

```sh
# Use the same local telemetry/analytics settings as above, plus:
# DAGGER_ENGINE=container://dagger-engine.rust-perf-f4e83a525
# XDG_{CONFIG,CACHE,DATA,STATE}_HOME set to isolated shared directories.
python3 hack/bench-rust-loop/compare-cli.py \
  --before /tmp/dagger-rust-cli-width-after --after /tmp/dagger-rust-cli-width-after \
  --before-workdir /tmp/dagger-rust-loop-k0_fv6tc/dagger \
  --after-workdir /tmp/dagger-rust-loop-4dqodx2f/dagger \
  --samples 30 -- check rust:check
```

APT median **399.84ms** [379.20, 522.87], pinned median **408.99ms**
[387.97, 502.71]. Difference of medians: **+9.15ms**. Median paired regression:
**+15.16ms**. Native profiling is off; local OTel remains enabled. Every sample
is in [the paired CSV](source-sync-delivery-warm-pairs.csv), where before=APT
and after=pinned. This comparison isolates repeated module invocation, not
Cargo performance or novel invalidation. There is no warm speedup claim.

wcprof confirms two HTTP revalidations on warm checks, each about 9-13ms in the
inspected traces, despite checksum pins. They overlap other work and are not
alone sufficient to explain the earlier 73ms batch regression. The slow warm
trace also has longer session/query/telemetry intervals. A potential follow-up
is reusing an already verified immutable HTTP snapshot when its requested
checksum matches, while retaining normal revalidation for unpinned requests
and session/auth isolation. This is a hypothesis/design direction, not an
implemented engine fix or established whole-command saving.

## Profiler validation and evidence

All four first-check OTel traces pass the maintained wcprof structural gate.
APT: 239 operations, 224/224 declared spans. Pinned: 269 operations, 254/254.
No missing/open operations, orphaned parents, unresolved waits, cycles, or
dropped links. Replay drift is -2.7%/-3.0% for the diagnostic pair and
-2.2%/-2.8% for the repeat. Treat cold counterfactual savings accordingly.

The two native first-check dumps have 829/880 operations, 8/10 roots, no
open/dropped events and +0.0% rounded replay drift. They do not cover the full
CLI lifecycle; root boundaries are also checked against process timers. The
inspected warm OTel traces pass with 132/152 operations and 117/137 declared
spans respectively; repeat replay drift is -1.6%/-0.1%.

Local evidence:

- /tmp/dagger-rust-loop-kfomt5cr and /tmp/dagger-rust-loop-yc43evmn (diagnostic pair)
- /tmp/dagger-rust-loop-k0_fv6tc and /tmp/dagger-rust-loop-4dqodx2f (repeat pair)
- /tmp/dagger-rust-cli-pair-d8i8tbam (30 alternating warm pairs)
- /tmp/dagger-rust-{apt,pinned}-sync-{first,repeat,warm-repeat}-* (traces, gates, boundaries, analyses)
- /tmp/dagger-rust-sync-packages.log (APT dependency resolution and hashes)

Python compilation and `git diff --check` pass. The full harness validates both
module branches, including the default APT branch after extracting the common
toolchain expression. No private analyzer source or raw credentials are added.
Build/export, clippy/fmt, additional projects, concurrency and cross-platform
coverage remain open. Cold Rust image delivery still dominates; this result
does not meet the Cargo-plus-one-second goal.
