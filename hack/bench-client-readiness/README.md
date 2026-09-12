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
The follow-up below validates application/library edits and an actual external
upgrade. Artifacts, remote engines and macOS remain unmeasured; cold behavior
does not yet support an overall promotion claim.

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
or completeness requirement was removed.

## Full-flow follow-up: warm gains, cold losses retained

Six fresh engine/Cargo/CLI states form three independent AB/BA/AB pairs. Both
sides use the same corrected experimental engine image above; only the matched
CLI differs. Each run includes three distinct application edits, three library
edits and one real bstr 1.12.0 → 1.13.0 upgrade. Native/Dagger upgrade order is
native/dagger/native across pairs and matched within each pair. No A→B→A
dependency cycling, listener or reused successful candidate edit is measured.

Milliseconds; warm rows summarize each run's three repeats before comparing
the three independent pairs. Upgrade/follow-up and first-use have one observation
per run. Marginal medians need not subtract to the median of paired differences.

| Scenario | Control median | Candidate median | Paired CLI saving (range) | Favorable pairs |
|---|---:|---:|---:|---:|
| First check, profiled | 13,746.678 | 15,669.866 | −1,202.881 (−3,045.505…−308.713) | 0/3 |
| Provision + first check, profiled | 13,965.786 | 15,916.767 | −1,232.494 (−3,056.393…−306.133) | 0/3 |
| Exact cached check | 524.998 | 446.459 | +78.539 (+67.674…+101.765) | 3/3 |
| Application edit | 894.276 | 832.093 | +52.638 (+43.852…+90.522) | 3/3 |
| Workspace-library edit | 1,051.883 | 982.306 | +63.191 (+58.784…+81.107) | 3/3 |
| Actual external upgrade, profiled | 2,229.327 | 2,162.757 | +66.570 (+31.458…+203.436) | 3/3 |
| Exact check after upgrade | 477.617 | 442.319 | +35.297 (−5.199…+39.448) | 2/3 |

Candidate medians against native: exact 446.459 vs 119.377 ms; application
832.093 vs 293.823; library 982.306 vs 460.130; upgrade 2,162.757 vs 1,649.798;
follow-up 442.319 vs 119.517. Median paired native overheads are respectively
330.587, 521.563, 522.511, 519.536 and 323.970 ms. The native-normalized upgrade
gain is only 9.735 ms, favorable in 2/3 pairs, unlike its larger raw CLI gain.
Provision + first-check candidate median paired native overhead is 9,304.534 ms.
**Every candidate flow still loses to native. The product goal remains unmet.**
Do not pool these three pairs with the earlier twelve-pair exact pilot or add
their gains to results from other engine/workload cohorts.

Cold regression inspection uses actual span envelopes, not simulated savings.
Pair 0's +1,202.9 ms process loss includes +1,001.3 ms connecting; its first
Control/Info takes 1,075.5 ms before the changed HTTP-readiness path is reached.
Pair 1's +308.7 ms loss includes +499.0 ms image delivery while connection time
is 5.0 ms lower. Pair 2's +3,045.5 ms loss includes +3,177.9 ms image delivery;
its large-layer stream grows from 3,383.9 to 6,475.4 ms, while connection time
differs by 0.2 ms. This localizes the observed costs; it does not prove an
environment-only cause or establish that the patch is harmless on cold flows.
No cold win or neutral result is claimed.

### Validation and interpretation

All six workflows exited successfully. All 36 wcprof captures have complete
declared/received spans and satisfy the structural/execution/byte gates;
18 cache snapshots were analyzed. Every one of 36 ordinary warm-edit rebuild
audits matches native: application edits rebuild only ripgrep; library edits
rebuild grep-printer, grep and ripgrep. All six actual upgrades select bstr
1.13.0, rebuild the same packages as native and exclude old bstr and unrelated
memchr. Restart exact checks execute no Cargo and transfer no image layers.

Cold captures have replay drift −4.8%…−7.3%, despite structural completeness.
Their counterfactual savings are not trusted. All other captures have drift
−0.0%…−0.1%. Use process clocks and actual enclosing spans for the cold losses.
The published [flow-report.json](flow-report.json) preserves every timing,
paired statistic, gate and drift; raw telemetry and private wcprof are retained
locally, not published.

The first offline analysis correctly rejected an expectation about the later
application *diagnostic*. That diagnostic follows library failure → repair →
failure revisit → cached successful repair → cached exact → application edit.
The successful immutable cache hit does not rewind Cargo's mutable target/source
cache left by the failed run, so this diagnostic rebuilds the three library
dependents too. It is not the ordinary timed application-edit scenario.
The second analysis explicitly checks that recovery package set; all ordinary
application samples retain the strict single-ripgrep gate. No runtime sample,
workload or timing was removed; both analyses are retained. This is Dagger cache
semantics, not a proposal to restore cache mounts on result hits.

### Scope and reproduction

Exact/edit/follow-up headline timers are unprofiled; first-check and upgrade
timers include profiling. Separate post-timer Cargo-diagnostic CLI invocations
occur on both treatments. Native is docker exec in the matched preinstalled
Rust image, not a bare-host Cargo comparison. CLI, engine image, local module,
Docker and native Rust image already exist. Host page/CDN caches are not purged;
native follows Dagger for initial check. This is not installation from nothing,
nor fmt/clippy/tests/build/export/macOS/remote evidence. Three repeats in each
run are not nine independent pairs; ranges are not population-tail estimates.

```sh
# Host-specific single-use controller: clone to fresh owned paths before rerun.
python3 /tmp/dagger-readiness-flow-pairs.lYuSmqQj/run.py --execute
python3 /tmp/dagger-readiness-flow-pairs.lYuSmqQj/analyze.py \
  /tmp/dagger-rust-cli-flow-ab-iarsbz2s
python3 /tmp/dagger-readiness-flow-pairs.lYuSmqQj/summarize.py
```

Controller e39d7e05f3946e2860a4613731580acb0e64061d1de10a780784508c3f2b20f3
uses unchanged adapter 629c75d15da8d187960ea19e2d79f31e3238079b14a17f4a889e3ce7a3e17c54.
Final analyzer 812011e1d5f6d895e242553dc8ad1eeec3834798d641e55afa22e011831e7194;
summary script 8c1986dfaa834273096b1733e6546e79f289d7302a58ece311c4db6aed00977a.
Raw telemetry: 42,689,273 bytes, SHA256
a609a2b2b0fb6982f21fec0682163c596d05751df09902c91983768c82776875.
Final analysis is `analysis-r2/report.json`; retained initial rejection is
`analysis/report.json`. Controller-owned receiver, six containers and state
volumes were cleaned up; retained baseline engines and frozen source untouched.
Current main was reverified as 6bf59d50654ce9244ebeee1cc090b7dce3fe3083.
