# CLI Unicode-table startup, 2026-09-10

## Context and change

The stack is rebased on upstream main f4e83a5250ca4aa392bacb3cd4b51bd9b50b2262.
The nine preceding branches were pushed atomically to the fork with explicit
leases; their range-diff was unchanged. No PRs were opened.

`GODEBUG=inittrace=1 dagger version` attributed about 23ms of startup to
go-runewidth v0.0.27 initializing two Unicode width lookup tables. This occurs
before the CLI root span, so a wcprof ranking alone cannot account for it.
Upgrade to the upstream v0.0.30 release, which initializes the larger tables
lazily and paints intervals instead of querying every rune individually.
Its package initialization measured 0.035ms in a separate diagnostic capture.

This is a dependency update, not a new Dagger cache, session, or execution path.
The release also contains upstream string/grapheme optimizations and fixes;
it is not accurate to describe every library behavior as unchanged. The
full-rune checksum expectations are unchanged between these two releases.
Upstream source: https://github.com/mattn/go-runewidth/tree/v0.0.30

## Matched comparison

Both comparison binaries use Go 1.26.6, CGO_ENABLED=0, identical build flags,
and source 0628f6d506995d14a6e6c6b52f151da35cbc65bb, with only the dependency
pin/checksums changed. Both are labeled dirty, not clean release binaries.

```sh
GOCACHE=/tmp/dagger-rust-go-cache CGO_ENABLED=0 go build -buildvcs=false \
  -ldflags '-s -w -X github.com/dagger/dagger/engine.Tag=0628f6d506995d14a6e6c6b52f151da35cbc65bb -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCS=git -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSRevision=0628f6d506995d14a6e6c6b52f151da35cbc65bb -X github.com/dagger/dagger/internal/version/buildinfo.InjectedVCSModified=true' \
  -o /tmp/dagger-rust-cli-width-after ./cmd/dagger
```

Build the before binary from the parent revision with the same flags and a
different output path. Recorded SHA256:

- Before: 7a4865d9f0b27ab660f2b9d0cfce75e0a56d9460c15ca02373eeb345e015ecb1
- After: 280da457914068c215f9bb8aada21a998f93b7ffd4ac4f17759c6943f5d06748

`compare-cli.py` excludes one warmup pair, alternates order, retains every
sample/outlier, records binary identities and whole-process times, and requires
successful exits. Both sides intentionally share the same workspace and
engine. This isolates a CLI change; it is not a cold or invalidation benchmark.

```sh
DO_NOT_TRACK=1 python3 hack/bench-rust-loop/compare-cli.py \
  --before /tmp/dagger-rust-cli-width-before \
  --after /tmp/dagger-rust-cli-width-after --samples 60 -- version
```

| Whole process, ms | Before median [min, max] | After median [min, max] | Median paired saving |
| --- | ---: | ---: | ---: |
| version, 60 pairs | 51.74 [49.96, 54.95] | 27.97 [25.57, 32.49] | 23.97 |
| check rust:check, 30 pairs | 419.29 [395.03, 487.50] | 407.95 [374.64, 474.76] | 25.61 |

For checks, the difference of medians is **11.34ms**, not 25.61ms. Runtime
variation is material; the median paired difference is a different statistic.
Do not promise a fixed whole-check saving from the startup result.

Check reproduction uses the pinned ripgrep workspace produced by `run.py`:

```sh
env -u DAGGER_CONFIG -u DAGGER_CLOUD_TOKEN -u DAGGER_CLOUD_URL \
  -u DAGGER_SESSION_PORT -u DAGGER_SESSION_TOKEN \
  -u OTEL_EXPORTER_OTLP_HEADERS -u OTEL_EXPORTER_OTLP_TRACES_ENDPOINT \
  -u CPUPROFILE DO_NOT_TRACK=1 \
  DAGGER_ENGINE=container://dagger-engine.rust-perf-f4e83a525 \
  XDG_CONFIG_HOME=/tmp/dagger-rust-lifecycle-4jdlbrae/cli-state/config \
  XDG_CACHE_HOME=/tmp/dagger-rust-lifecycle-4jdlbrae/cli-state/cache \
  XDG_DATA_HOME=/tmp/dagger-rust-lifecycle-4jdlbrae/cli-state/data \
  XDG_STATE_HOME=/tmp/dagger-rust-lifecycle-4jdlbrae/cli-state/state \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:43181 \
  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://127.0.0.1:43181 \
  OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:43181 \
  OTEL_EXPORTER_OTLP_TRACES_LIVE=1 \
  python3 hack/bench-rust-loop/compare-cli.py \
    --before /tmp/dagger-rust-cli-width-before \
    --after /tmp/dagger-rust-cli-width-after \
    --workdir /tmp/dagger-rust-loop-4riktc0e/dagger \
    --samples 30 -- check rust:check
```

Start the local-only OTel receiver first, following the telemetry-capture
skill. The XDG directories were isolated from real cloud credentials and
shared across both sides. Analytics is disabled, local OTel is enabled, the
frontend is the default report frontend under this runner, and native wcprof
`--profile` is disabled for the paired timings. These are not measurements of
the interactive TUI or the default authenticated-cloud/analytics configuration.

The engine was rebuilt through the pinned dev deployment workflow on current
main, with the debug endpoint not published to avoid the existing engine's
port. Its image is localhost/dagger-engine.rust-perf-f4e83a525, image ID
sha256:b0d48e4e9658afc010826a5d55be93415af89b1d6465add68bb8d03df6f4cc0b,
and embedded VCS revision is 0628f6d506995d14a6e6c6b52f151da35cbc65bb.
The engine uses Go 1.26.8; both compared CLIs use Go 1.26.6.

## wcprof and correctness

The final paired check is deliberately not cherry-picked for a whole-command
win: before was 407.68ms and after was **417.02ms**. Before the CLI root span,
however, the interval fell from 52.30ms to 28.61ms. Root duration varied from
345.48ms to 377.76ms and teardown from 9.90ms to 10.65ms.

Both traces pass the maintained wcprof structural gate: 132 operations, one
root, 117/117 declared spans, no missing/open operations, dropped links,
unresolved waits, orphaned parents or cycles. Replay drift is -0.1% before
and rounds to -0.0% after.
This separates the startup improvement from unrelated runtime variation.

Passed checks:

```sh
GOCACHE=/tmp/dagger-rust-go-cache go test github.com/mattn/go-runewidth -count=1
GOCACHE=/tmp/dagger-rust-go-cache go test -race github.com/mattn/go-runewidth \
  -run '^TestRuneWidthConcurrent$' -count=1
GOCACHE=/tmp/dagger-rust-go-cache go test ./dagql/idtui -run '^TestASCIIReporter' -count=1
python3 -m py_compile hack/bench-rust-loop/compare-cli.py
git diff --check
```

The concurrent test runs alone to exercise first-use lazy initialization.
The library suite includes full-rune checksums, LUT/reference comparisons,
and string/grapheme/wrapping tests. A separate live TUI-console smoke check
returned a successful rust:check and correctly displayed the check group,
Unicode status glyphs and navigation footer. This is not broad terminal QA
or macOS validation; asciinema was unavailable in this environment.

The candidate CLI also passed the full pinned ripgrep failure/repair/old-failure
revisit and external bstr 1.12.0 -> 1.13.0 harness. Both sides rebuilt the same
10-package set and retained memchr. The diagnostic dependency upgrade took
2092.30ms (native via docker exec: 1725.39ms); this is a profiled validation,
not a matched A/B speedup. Its startup interval is 28.55ms. The OTel gate
passes with 158 operations and 143/143 declared spans; native wcprof has 488
operations, eight roots, no open/dropped events and -0.0% rounded replay drift.

## Evidence and remaining gap

All raw samples, including warmups, are retained in:

- /tmp/dagger-rust-cli-pair-6qpq9t6s (version, 60 pairs)
- /tmp/dagger-rust-cli-pair-n_54urx1 (check, 30 pairs)
- /tmp/dagger-rust-width-{before,after}-{trace.jsonl,boundaries.json,analysis.txt,gate.txt}
- /tmp/dagger-rust-loop-bl70e_69 (candidate correctness/invalidation)
- /tmp/dagger-rust-width-invalidation-* (both profiler backends)
- /tmp/dagger-rust-width-{library,race,render}-tests.log
- /tmp/dagger-rust-f4-init.log and /tmp/dagger-rust-width-after-init.log

These paths are local artifacts, not publicly hosted captures. This commit
does not establish full first-install, build/export, remote-engine or macOS
performance. The latest preceding current-main engine-cache-cold check plus
provisioning was 40.56s versus native's first check at 6.04s. Its wcprof ranking
put HTTP fetching at about 23.23s and unpacking at 4.44s. The CLI improvement
does not solve that gap; toolchain delivery and the Rust module remain major
work items. The previously observed 262ms post-root exit delay was not
reproduced with isolated CLI state; no teardown fix is claimed here.
