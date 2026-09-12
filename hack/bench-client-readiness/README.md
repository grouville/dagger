# Experiment: overlap independent client-connection readiness

This branch targets ordinary standalone CLI latency. It is based directly on
main 6bf59d50654ce9244ebeee1cc090b7dce3fe3083, not on the image-streaming source
patch. The performance pilot used the separately recorded experimental engine
stack; this branch alone does not reproduce that stack or the full Rust demo.
No PR, maintainer approval or complete dev-loop performance fix is claimed.

## Context and change

After session initialization, telemetry opened its HTTP/2 connection while the
foreground transport stayed lazy until the first query. Existing profiles showed
about 40 ms of first-request transport readiness, despite Connector.Connect
returning in less than 1 ms. A returned Docker tunnel is not yet a ready server.

The change makes an existing POST /init request on the foreground transport
while the separate telemetry transport subscribes. Both must finish before
Connect returns. /init finds the already-initialized client and returns 204;
workspace/module loading remains in serveQuery. It neither runs Cargo nor
changes egraph/cache identities, source inputs or session reuse boundaries.
No listener, pre-existing CLI session, telemetry opt-out or shared connection
pool is introduced. This is overlap within the measured invocation, not prewarm
outside its timer.

Foreground and telemetry retain their independent lifetime rules. On setup
failure the new request is canceled/joined and normal Close performs shutdown
and telemetry draining. /init now rejects non-success HTTP status codes and
closes their bodies. Non-nested Connect uses the scheduling change (not just
main-session callers); nested connection order and ConnectEngineToEngine are
unchanged. With no telemetry consumers, the foreground transport stays lazy.

## Exact-hit pilot: measured, not an invalidation result

Twelve unprofiled alternating pairs on the same retained corrected engine and
same prepared ripgrep workspace, with matched CLI builds and no concurrent heavy
work. Each command is a new standalone `dagger check rust:check` process.

| Measure | Control | Candidate |
|---|---:|---:|
| Median process time | 481.196 ms | 445.897 ms |
| Minimum | 446.942 ms | 427.567 ms |
| Maximum | 575.681 ms | 484.255 ms |

**Paired median saving: 29.661 ms; 10/12 favorable.** Paired savings range from
−20.799 to +127.523 ms. Preserve both losses and the favorable outlier; do not
attribute all variability to the patch or treat this range as a tail estimate.
The candidate remains much slower than the earlier approximately 118 ms native
reference; this experiment has no new paired-native claim.

The initial warmup pair is excluded on both sides: control 23.906346 s primed
the engine/project, candidate 447.584 ms reused it. It is **not** a cold comparison
or an onboarding win. Only subsequent exact-cache pairs establish this result.
Application/library edits, actual external-dependency upgrades, artifacts,
remote engines and macOS still need matched validation before promotion.

Three separate profiled pairs plus a diagnostic warmup produced eight complete
wcprof captures. Every capture has 169 operations, no open/dropped operations,
154/154 declared/received engine spans, zero actual Cargo executions, and the
same three Container.withExec cache hits. Replay drift is 0.0% to −0.1%.
Checks-to-first-query gaps are 38.018–78.246 ms on control and 0.395–0.790 ms
on candidate (including diagnostic warmup). /init has no separate span here,
so these captures do not independently measure its full connection overlap;
the HTTP/2 barrier tests establish concurrency and whole-process timings decide
the gain. The larger 76.612 ms paired saving in the three profiled pairs is
diagnostic only, not the headline result.

[exact-report.json](exact-report.json) preserves all twelve unprofiled pairs,
every separate profile gate and process/root accounting. Maintained private
wcprof code and raw telemetry are not published.

## Correctness and reproduction

The added focused tests use real loopback HTTP/2 connections and barriers:
simultaneous readiness, foreground reuse with separate telemetry, final event
delivery after foreground shutdown, rejected init/subscription responses,
canceled initialization, lazy behavior without exporters and body closure.
The cancellation test waits until both handlers have started. Ten race-enabled
repetitions passed on the measured source; the same tests plus existing client
metadata tests were rerun on this direct-main publication branch.

```sh
go test -mod=readonly -race ./engine/client \
  -run '^(TestHTTPReadiness|TestClientMetadata)' -count=10 -timeout=90s
```

This is focused validation, not exhaustive reconnect/failure cleanup, remote or
cross-platform certification. Existing telemetry intentionally outlives caller
cancellation; the patch does not replace that policy with an errgroup context.

Retained experiment root: `/tmp/dagger-client-ready-overlap.xfvJBun1`.
Measured source parent db9d005c715ac9d146780d783faf7f7b55d23e5e is an experimental
stack on the same main revision. Its original client.go is byte-identical to
main's; the publication candidate and test file match the measured bytes.

```sh
# Host-specific, single-use scripts: fresh owned paths/pins needed for a repeat.
bash /tmp/dagger-client-ready-overlap.xfvJBun1/build-cli.sh --execute
python3 /tmp/dagger-client-ready-overlap.xfvJBun1/pilot.py --execute
python3 /tmp/dagger-client-ready-overlap.xfvJBun1/profile.py --execute
python3 /tmp/dagger-client-ready-overlap.xfvJBun1/analyze.py
```

Both CLIs use Go 1.26.8, linux/amd64/v1, CGO=0, identical trimpath/ldflags/source
path and dependencies. Control uses a read-only overlay of original client.go;
build metadata differs only in output filename. Race tests use CGO=1. No engine
is rebuilt/replaced/reset for this pilot; the exact engine identity is checked
before and after. Preparation created only an owned project/cache namespace and
CLI-state directory. The diagnostic receiver is stopped after capture.

| Pin | SHA256 or immutable ID |
|---|---|
| Engine | 848627df950f9d0211436e3210bbbf34ba97f7a1823a528880c5dace238d9a2c |
| Engine container | 770926d889a5e371be2da9644a5f20752cd6ec2380e36c71a5d24ec72c289369 |
| Control CLI | 61e4855dbd20d9fcd992ca45d49a3fe085617b8279796fa444975ca35dec865c |
| Candidate CLI | 98fc6ea8e60fc574117300dce9334d008ee4317ee35bce5a8eebe03455110d3a |
| Candidate client.go | c26470f730c3879c6ba03e1ced6cea08c3a70f3d87463d3b8d769e0a4fd3c8e2 |
| http_readiness_test.go | 6fba76b23e0b106ffa80febfe65a9cf3d70e22e63893cd047a68530807c61aef |
| Exact report | 8e379caa6e9047d9cb9ea5f93b33b54d5a9de4af8be0ef4362abe718b6c6743c |
| Raw profile telemetry | 90db9c25a10dba04e72414822ed793a6afa51afe5e8ac137b15fbd4b1cc4a343 |

Unprofiled process/CSV corpus: `/tmp/dagger-rust-cli-pair-udrbfp8j`.
Separate profiled corpus: `/tmp/dagger-rust-cli-pair-lj5aid7k`.
Final analysis: `analysis-r3/report.json`; first analysis failed due to a duplicate
label keyword, second passed structural/exec gates but its cache-outcome selector
was empty. The final pass uses Dagger's actual cache-outcome attribute and requires
all three hits. Both earlier analysis directories are retained; no timing sample
or completeness requirement was removed. Next gate is genuine invalidation,
not another exact-hit-only victory claim.
