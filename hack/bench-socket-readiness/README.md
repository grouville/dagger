# Unix-socket startup readiness

This experiment targets an ordinary first-connection delay, not a new resident
CLI or cache. The proposed code changes only `cmd/dialstdio` and its tests, on
main `6bf59d50654ce9244ebeee1cc090b7dce3fe3083`. Measurements use reviewed stack
`db9d005c715ac9d146780d783faf7f7b55d23e5e`; the helper source is identical between
that stack and main before this change. The fixed CLI is identical on both
sides. Neither side includes the separate parsed-source or image-stream patch.

## Cause and fix

`docker run -d` can finish before the engine binds its Unix socket. The stdio
helper previously called `net.DialTimeout` once. Missing/not-listening Unix
sockets fail immediately, rather than waiting for the socket to become ready.
The helper exits, and the parent gRPC connection enters its normal initial
one-second backoff. `WaitForReady` avoids another polling delay but does not
remove transport reconnect backoff.

The helper now waits within **one total positive timeout**, retrying only
wrapped `ENOENT`/`ECONNREFUSED`. It attempts immediately, then backs off 5/10/20/
40 ms to a 50 ms cap. Successful/ready connections add no sleep. Other errors,
including invalid protocols and permission failures, do not retry. Zero and
negative timeouts retain the original one-shot `DialTimeout` semantics; zero
is not an unbounded readiness retry.

The deadline ends with dialing and does not affect the established connection,
copying or half-close paths. Global gRPC policy, remote transports, session
ownership, graph identities and cache behavior are unchanged. Cancellation
continues to be owned by the outer transport/process lifecycle; this patch does
not add signal handlers or consume stdin to detect cancellation.

Intentional error-UX tradeoff: a persistently missing or stale socket now waits
up to the existing default five-second timeout before failing, rather than
immediately. Timeout diagnostics retain the address and last socket error.
This behavior is not described as compatibility-neutral.

## Baseline evidence

A focused delayed-listener regression failed against the old implementation at
0.00 s with `ENOENT`, before the listener was created. More importantly, six
actual fresh-engine standalone query diagnostics, with **no injected startup
delay**, each recorded one stdio helper exiting because `/run/dagger/engine.sock`
was absent, followed by gRPC `TRANSIENT_FAILURE` and a reconnect about one second
later. Initial `Info` calls took 1,076–1,086 ms; whole diagnostic queries were
approximately 1,617 ms. All six wcprof structural gates passed, with replay
drift rounded to −0.0%.

These use `--debug --profile` plus gRPC logging; they are diagnostic queries,
not Rust workload timings or a claimed one-second before/after gain. A long
Info span alone would not prove this cause: a server returning `Unavailable`
can also produce a one-second wait. The retained logs directly show the failed
helper dials, resolving that ambiguity for these six diagnostics.

## Focused validation and build

```sh
go test -mod=readonly -race ./cmd/dialstdio -run '^TestDialer' -count=10 -timeout=30s
```

Ten race-enabled repetitions passed using pinned Go 1.26.8. Coverage includes
delayed missing and stale sockets, a bounded readiness timeout, invalid/non-
transient cases, zero/negative timeouts, and an established Unix connection that
outlives the dial deadline and still supports half-close in both directions.
The tests do not certify every cross-process cancellation or remote platform.

The first candidate test attempt used the wrong Go timeout sentinel for a
negative `DialTimeout`; it was corrected to check the standard `net.Error`
timeout contract. The original one-shot runtime behavior was not changed to
satisfy that assertion. The failure log is retained.

The first supported dev build failed because a shared Git clone's object
alternates were outside the uploaded source. No VCS check was disabled. A
self-contained shallow clone at the exact same commit, with byte-identical
tested source files, built successfully through the supported dev workflow and
passed its query smoke check. Both build attempts and their manifests remain.
Build/setup time is not a performance measurement.

## Reproduction

Retained owner: `/tmp/dagger-socket-readiness.ihqhDhKJ`. Scripts are single-use
and require fresh owned paths for another run; they refuse to overwrite old
captures/build attempts. Existing engines and user worktrees are preserved.

```sh
# Diagnostic control only, not a paired Rust benchmark:
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/probe.py --execute
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/analyze-probe.py

# Supported candidate deployment, then matched real Rust flows:
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/build-r2.py --plan
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/build-r2.py --execute
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/run.py --execute
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/analyze.py COHORT
python3 /tmp/dagger-socket-readiness.ihqhDhKJ/summarize.py COHORT
```

The Rust comparison keeps the existing pinned ripgrep module, image, toolchain,
source filters, Cargo command and correctness gates. Three independent AB/BA/AB
engine pairs have fresh engine/Cargo/CLI state, three novel app and three
workspace-library edits, one real bstr 1.12.0→1.13.0 upgrade, failure/repair/revisit
checks, and engine restart. Repeats are summarized within each run before paired
comparison: not nine independent pairs.

Cold first-check and external-upgrade times include wcprof; other timed warm
flows do not. OTel capture and post-timer diagnostic sessions are matched.
Structural capture acceptance does not certify accurate replay what-ifs.
Cargo/native package equality, unchanged reusable crates, image byte totals and
failed-source behavior must pass before interpreting timings.

Limitations: CLI, Docker, engine image, module and native toolchain image are
preinstalled. Native uses `docker exec`, not the bare host; host page/CDN caches
are not purged. No full-install, artifact export, fmt/Clippy/test-command,
macOS or remote performance claim. No sum with other experimental cohorts.

## Completed comparison: not promoted

All 36 wcprof captures, 18 cache analyses and 36 ordinary warm crate audits
passed. Replay drift was −0.0% to −0.1% for warm/restart captures and −4.5% to
−4.8% for cold captures; cold what-if savings are not accepted quantitative
predictions. Each of the six owned runtime groups was independently verified
absent after the adapter cleanup. Main was reverified at the above commit.

Positive savings mean this candidate was faster; these are three paired
per-run summaries, not independent per-edit samples:

| Flow | Median paired CLI saving ms | Range ms | Favorable pairs |
| --- | ---: | ---: | ---: |
| First check (profiled) | 357.632 | −316.554 to 584.324 | 2/3 |
| Provision plus first check | 335.346 | −328.562 to 590.751 | 2/3 |
| Exact unchanged | −2.976 | −13.497 to −0.256 | 0/3 |
| Application edit | −39.841 | −42.236 to −31.284 | 0/3 |
| Workspace-library edit | −15.202 | −29.752 to −9.603 | 0/3 |
| External upgrade (profiled) | 58.984 | 21.385 to 106.458 | 3/3 |
| Upgrade followup | 21.248 | −4.844 to 29.033 | 2/3 |

Every measured candidate flow remains slower than native. Candidate medians:
18.130 s provision plus first check; 450 ms exact, 863 ms application edit,
993 ms library edit, 2,175 ms external upgrade, 450 ms upgrade followup.
Native-normalized median savings for provision plus cold were **−2.437 ms**;
application and library overhead regressed 41.004 and 17.042 ms respectively.
Do not dismiss consistent edit regressions as noise or attribute upgrade gains
to readiness without further causal evidence.

Only the middle control run had the long connection in this cohort: 1,512 ms
versus 474 ms for its candidate. All other control and candidate connections
were 461–472 ms. Removing that retry did not imply an equally large full-flow
gain: Cargo and image timing varied. The first pair's image delivery was
780 ms faster while Cargo was 498 ms slower; the last pair's delivery was
591 ms slower while Cargo was 335 ms faster. These observations explain why a
single cold median is not a clean readiness attribution.

This branch preserves an experiment, **not an accepted broad performance fix**.
Before promotion, also validate actual cross-process cancellation: Docker
commandconn closes/kills its CLI transport, but the remote exec helper might
outlive it until the bounded five-second readiness timeout. Unit half-close
tests do not establish that ownership guarantee. That gate is deferred while
performance work returns to larger cold-delivery costs.

The publication checkout passed the same focused race test with count=10.
An initial sandboxed attempt failed socket creation with operation-not-permitted;
that log is retained separately from the permitted successful run.

Retained evidence:

- Cohort: `/tmp/dagger-rust-socket-ready-ab-cppa70sc`.
- `comparison.json` contains the scope, limitations, individual samples and all
  paired flow summaries, excluding the bulky duplicated profile detail. The
  full local `OWNER/summary.json` SHA256 is
  cddc5e8f7a090f23e9ea64ab6939ac55d957d7c04c5b9c352b0d3622793b6683.
- Full local report: `COHORT/analysis/report.json`, SHA256
  efef1b569ca370524fb6ac1648c71adb69b15cb850f656bdc3bdf2c35e94f797.
- Raw local OTel: `OWNER/flow-telemetry.jsonl`, 42,649,765 bytes, SHA256
  0a611d0aa2e6564e87021ebb9027b7765a5688252870588f09ae096be41f3a57.
- All candidate/control logs and build attempts remain under the retained owner.

No private analyzer binary or raw telemetry is included in this branch.
