# Raw HTTP transport preparation: local CLI experiment

Status: measured local Docker exact-hit improvement, **not promoted**. No cold,
native-parity, edit, artifact-export, macOS or remote performance claim.

## Context and change

The preceding boundary diagnostic measured approximately 125–130ms connecting
each ordinary standalone CLI process. A Docker version probe was followed by
BuildKit readiness, session attachables, then separate foreground/telemetry HTTP
connections. Five host Docker processes were observed (version + four tunnels).
The syscall-instrumented exec-to-first-daemon-connect interval was 13.006ms median
for 36 tunnels, not pure CPU or a removable end-to-end saving. Nine traced runs
were substantially perturbed; none are headline timings. All eighteen separate
wcprof traces passed completeness and real-crate execution gates.

This change prepares the two raw HTTP transports after engine readiness and
package/version validation, concurrently with session attachables. It sends no
HTTP request or HTTP/2 preface until that handshake finishes. A prepared raw
connection is claimed once through the existing HTTP/2 DialTLSContext callback;
later reconnects retain the normal connector and HTTP/2 pool. It creates no
additional connection on a successful ordinary path and does nothing when no
telemetry consumer is configured. Nested/E2E scheduling is unchanged.

Foreground and telemetry remain separate. Cancellation closes and joins unused
or late-returned preparations. Successful handoff preserves the actual net.Conn
type, including *tls.Conn; HTTP/2 owns shutdown of consumed connections. Telemetry
is drained before its transport closes and its retained dial context is released.
An unused TLS transport is aborted through its raw connection, avoiding a blocked
close_notify. No cache identity, egraph, leases, result lookup or execution work
changes; no listener, persistent CLI or speculative extra session is introduced.

## Latest-main pilot (2026-09-12)

Base: upstream 7c35e6274737acff0f6bd76614abb5e04efa7d12 plus readiness prerequisite
350e22edd9485fa76fd4bb0c564b21a44b01fb6a (replayed from 31880c94). Both binaries
were rebuilt from this base with identical flags. Control overlays the
pre-preparation client.go and excludes http_preconnect.go. The existing separate
readiness improvement is present on BOTH sides; do not add its earlier savings.

| Ordinary cached `check rust:check` | Control | Candidate |
| --- | ---: | ---: |
| Median CLI wall time, ms | 456.050 | 417.675 |
| Observed min–max, ms | 433.644–641.883 | 405.343–440.440 |

Twelve alternating pairs, one separately recorded warmup pair. Median **paired** saving
32.4538855ms [18.249495,206.875582], 12/12 favorable. Difference of column medians
is not the paired statistic. No samples discarded. Small local sample, not
evidence of stable population tails or a complete Rust dev-loop victory.

Separate profiled sequence: three alternating pairs plus a warmup pair; all eight
wcprof structural/completeness, exact-cache and no-execution/no-image-transfer
gates pass. Replay drift −0.0..−0.1%. Actual Cargo executions: zero, as expected
for an exact hit. Non-warmup candidate trace-subscription readiness is
0.778–1.315ms versus 34.827–56.696ms in controls. Full connection savings are
11.584–69.572ms across those three pairs. Moved/overlapped work is not free work;
profiler spans cannot be summed as independent savings.

This is not an invalidation benchmark. Edits, external upgrades, errors/repair,
first-use provisioning and artifact flows need the fullflow suite with this
change. Native Cargo was not timed here. The module is the existing minimal
Rust check fixture, not a validation of the complete official module.

The engine is unchanged image3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181,
container ff1caa52447eaf97c9b97b1d7b8765b3679bb956af1298821759dab0e29b6f1e.
It is the retained earlier experimental engine, NOT a newly rebuilt complete
latest-main stack. The upstream advance changed release/version/generated docs,
not these client/server transport implementations. Full-stack rebuild remains
required before promotion; older published branches are preserved.

## Validation and adverse evidence

Focused latest-main tests passed `-race -count=10`:

```sh
go test -mod=readonly -race -count=10 -timeout=120s ./engine/client \
  -run '^Test(PreparedHTTP|HTTPReadiness)'
```

Tests cover raw-connection identity, normal redial, one-time handoff, late-return
cleanup, canceled consumer, dial error, no early request, separate HTTP/2
transports and telemetry after foreground shutdown. A completed real TLS
handshake with a non-reading peer gates unused-connection abort. This does NOT
establish all remote lifecycle behavior or platform performance. Supported
engine-dev integration and failed-start/concurrent-session gates remain needed.

Initial valid pilot on the preceding base/cleanup draft: 29.704272ms median
paired saving, 10/12 favorable, range −762.852472..93.509367ms. Candidate had a
1.486429s sample versus control maximum0.723576s. Retained in
initial-pilot-report.json; cause of the tail is not established. Its direct TLS
close ownership was corrected before the latest-main run. Do not pool cohorts
as an unchanged-candidate sample.

First attempted pilot was rejected before the candidate ran: its copied project
omitted Git initialization, allowing the control to walk the broader /tmp
workspace. The owned control was stopped with SIGQUIT; its stack shows filesync
walking that boundary. Original scripts/logs remain local. Fresh runs assert
their Git root. This was a harness failure, not a credited engine speedup.
A scratch clone also initially lacked the FETCH_HEAD-only latest-main object;
that scratch cherry-pick was aborted and the object fetched before successful
replay. No original branch was reset.

Boundary diagnostic cold setup took56.446s, with a40.440s mirror.gcr.io GET.
That mirror is generated by .dagger/modules/engine-dev/config.go: a dev-engine
route, not a verified production default. Its cold replay drift was−1.7%; no
fully gated new cold score is claimed. Local-registry codec/stream results do
not establish public-registry onboarding latency.

## Exact local reproduction and evidence

See [FULLFLOW.md](FULLFLOW.md) for the subsequent real edit/dependency/cold
matrix: application/library edit wins, mixed dependency results and cold losses.

The local-build.sh, local-control-overlay.json and local-pilot.py record the
measured environment's exact paths; adapt constants/output directories for
another host. Obtain control-client.go from the prerequisite commit. The pilot
uses the existing compare-cli.py harness from the retained pinned benchmark
checkout, initializes an independent Git-rooted ripgrep copy, alternates CLI
order, retains every timing and owns its OTLP receiver. It intentionally does
not reset the engine: this is a warm exact-hit experiment.

```sh
bash /tmp/dagger-http-preconnect-main.tRLouH4d/build.sh
python3 /tmp/dagger-http-preconnect-main.tRLouH4d/pilot-r2.py --execute
python3 /tmp/dagger-http-preconnect-main.tRLouH4d/analyze.py \
  /tmp/dagger-http-preconnect-main.tRLouH4d/pilot
```

Exclusive result directories refuse to overwrite a run; choose a fresh owner to
repeat. Go1.26.8, unchanged dependency locks, `-buildvcs=false -trimpath`, identical
explicit linker VCS/version values. Control binary SHA256
909120fbf82945488e3b089d527fba0455db1cacdd993bce40bd81071132ddb6;
candidate23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270.
Build-source hashes are retained in build-inputs.sha256.

Latest unprofiled root /tmp/dagger-rust-cli-pair-8as921bw;
profiled root /tmp/dagger-rust-cli-pair-r50mir6y.
Raw OTLP1820627bytes SHA256 d509bd57b025f150a97deb5b7559770b55807a0553d457f64507b5a9d5d143a0;
report02b38878377d7ab8192efe97be41fd0f90b9b64fabb6b3bc84e8fe9aa6497830;
testlogf0804a143f661120f0eefe150bf410ca0b3aa02b4f3c4817e12cd33a221944ac.
Sources/derived profiles/gates remain under the latest owner. Receiver stopped
normally with SIGTERM; engine identity independently checked before/after.

Earlier pilot owner /tmp/dagger-http-preconnect.CU7R4qkx;
valid roots /tmp/dagger-rust-cli-pair-09e31xh2 and /tmp/dagger-rust-cli-pair-s6ojdbyy;
failed root /tmp/dagger-rust-cli-pair-z4xilx4s. Exact measured production/test
sources were reconstructed in r2-source and verified byte-for-byte against the
pre-build SHA manifest. Report SHA256
33fec987c6a2ee3cd5406627865de3fb1ed05692d27f56233f5772542897eed0.
Boundary owner /tmp/dagger-cli-boundary.xhm0GWRY:18 complete diagnostic traces,
45 observed Docker process/socket attributions, seven undecoded syscall records
retained, no unassociated recorded Docker socket connects. Its first offline
analyzer duplicate-key failure is retained; separate v2 passed without rerunning
the capture. Maintained wcprof executable and raw captures remain local.
