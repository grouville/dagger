# Smaller toolchain evaluation, 2026-09-10

## Context and change

The complete cold trace ranked downloading and unpacking the official Rust
image ahead of Cargo. Evaluate the official 1.97.1 slim-bookworm variant using
the existing `--image` option, without changing source, compiler version, Cargo
flags, session lifetime or cache semantics. No universal default is changed.

Linux/amd64 registry manifests:

| Image | Compressed layer bytes | Layers |
| --- | ---: | ---: |
| rust:1.97.1-bookworm | 566462087 | 5 |
| rust:1.97.1-slim-bookworm | 316873658 | 2 |

This removes 249588429 compressed bytes (44.1%). The slim variant's large layer
still contains a real compiler, standard library and system C toolchain.

## Reproduction

Use the CLI built at e80290410 (readiness change), the same locally built main
engine image as `first-use-results.md`, and a clean ripgrep checkout at
3fce3b5bb0236da2df6d99672afb8a719642eca7. Start the skill's otlpdump receiver on
127.0.0.1:43180, then run from the engine checkout:

```sh
env OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:43180 \
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:43180/v1/logs \
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:43180/v1/metrics \
    OTEL_EXPORTER_OTLP_TRACES_LIVE=1 \
    python3 hack/bench-rust-loop/run.py \
    --dagger /tmp/dagger-rust-cli-readiness \
    --image rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b \
    --ripgrep /tmp/dagger-rust-ripgrep-reference \
    --samples 5 --fresh-engine localhost/dagger-engine.dev --profile-first
```

The native-control image must already be installed in Docker. Dagger downloads
and unpacks independently into each new engine volume. Engine image, CLI, local
module and Docker are preinstalled; host page cache and network caches are not
reset. This is empty-engine onboarding, NOT complete new-user installation.
The digest above is amd64-specific for this experiment, not a cross-platform
module default. Official manifests also expose an arm64 variant; it was not run.

## Observations

Two sequential slim trials, not a randomized cold A/B distribution:

| Boundary (ms) | Slim first | Slim repeat |
| --- | ---: | ---: |
| Provisioning through first check | 28251.62 | 32095.56 |
| CLI first check | 28016.21 | 31888.82 |
| Image download | 9524.74 | 13956.21 |
| Image unpacking | 4766.93 | 4631.59 |
| Native first check (docker exec) | 7698.01 | 6324.32 |

Full-image cold checks in the preceding two profiled trials took 36.72s and
43.54s; unpacking took 10.74s and 10.27s. Only the latter used the readiness
candidate. Download variance is substantial: the repeat slim download was
slower than the preceding full-image download despite fewer bytes. The robust
signal worth following is lower bytes and roughly halved unpack time; do not
attribute the entire end-to-end delta to the image change.

Repeat warm medians (five paired samples each):

| Scenario | Native ms | Dagger ms |
| --- | ---: | ---: |
| Exact source | 153.34 | 682.36 |
| Application edit | 310.75 | 1052.14 |
| Workspace-library edit | 588.21 | 1255.42 |

Both runs passed compile-error detection, repair and revisiting old failing
source, and removed their disposable engine/volume. These are not dependency
version upgrades, artifact builds, full checks or host-native Cargo comparisons.

## wcprof and remaining limitations

Both OTel structural gates PASS: one root, no missing/open operations, orphaned
parents, cycles, unresolved waits or dropped links; 224/224 declared spans
received. Replay drift is -2.8% and -2.2%. Native dumps are retained alongside
each run. No private analyzer source or raw telemetry is published.

Local evidence: /tmp/dagger-rust-loop-od7okdhc (two warm samples),
/tmp/dagger-rust-loop-_b4yrxj2 (five), /tmp/dagger-rust-slim-first-trace.jsonl,
/tmp/dagger-rust-slim-repeat-first-trace.jsonl, and matching *otel-analysis.txt.

Inspection finds cc available but no git, pkg-config, rsync, clippy or rustfmt
components in the slim base. Runtime apt still installs rsync. This fixture
works, but native-library projects need explicit packages; a complete official
module also needs check-tool delivery. A smaller, configurable toolchain image
is promising, not yet a drop-in solution for every Rust project.

The cold overhead target is still unmet. The next packaging experiment must
count rsync/check-tool image delivery, rather than moving setup outside the
timer. Separately, warm CLI wall time exceeds the root span by around 300ms;
measure startup/exit boundaries before attributing this to engine execution.
