# CLI readiness: measured startup fix, not a solved Rust workflow

Base CLI f7dc1f5a4184 contains upstream main7c35e6274737, reverified before
measurement and publication. This branch changes only Client.Wait in production;
the tests and benchmark evidence are separate. No listener, cross-invocation
process cache, egraph bypass, engine patch or image-stream dependency is required
by the readiness fix itself.

## Context and behavior

An engine whose Unix socket is briefly unavailable can make fail-fast Info return
Unavailable. Wait then sleeps one second, resets asynchronous transport backoff,
and probes immediately. That probe can observe the old transport failure and
sleep another second. Earlier default-registry cold traces exposed this path.

The old experimental098a09a4b691c5c0d3f530abec6fa1a4ebc5ffbb commit already added
per-Info grpc.WaitForReady. It was present in the measured engine source but absent
from the current standalone CLI. This is a reconciliation and revalidation of
that change, not a claim to have newly discovered it.

WaitForReady wakes the RPC when the transport is ready. Actual Unavailable replies
from a connected server retain their one-second application retry. Queued
transports now follow configured gRPC reconnect backoff, without the old periodic
application ResetConnectBackoff. Global settings are unchanged, but persistent
outage retry timing is not identical. The initial gRPC reconnect delay remains.

Queued cancellation exposed a gap in the older change: local cause identity was
lost inside gRPC. For cancellation/deadline statuses only, return context.Cause
when the local context has ended. Preserve live-context server statuses, success,
Unimplemented compatibility and other errors. Both readiness and subsequent
engine-version validation Info calls remain.

## Primary comparison: ordinary CLI-managed engine lifecycle

The standalone CLI creates each fresh engine through image+docker inside its
first-command timer. Warm commands retain that same driver and its lookup/start
work. There is no artificial readiness delay. Both CLIs use the identical
previously validated experimental stream engine image, official gzip Rust image,
original modulef6e and default packaged registry route. No parser-statistics
prototype. Three independent AB/BA/AB pairs; within-run warm repeats are summarized
before pairing. All observations, including regressions and outliers, are kept.

Times below are milliseconds; positive paired savings favor B. Differences of
separate medians are not the paired median. First check already includes engine
provisioning: the two first-use fields in results.json are identical, not additive.

| Flow | A median | B median | Paired saving median [min, max] | Favorable |
|---|---:|---:|---:|---:|
| CLI-created engine + first check, profiled | 23237.102 | 20096.958 | -35.899 [-26790.549, 5598.298] | 1/3 |
| Exact check | 559.472 | 561.959 | -3.521 [-9.803, 68.132] | 1/3 |
| Application edit | 947.980 | 938.722 | 9.877 [0.649, 92.624] | 3/3 |
| Workspace-library edit | 1120.911 | 1100.719 | 27.828 [-7.622, 4083.587] | 2/3 |
| bstr1.12 ->1.13, profiled | 2388.273 | 2247.411 | 140.614 [-5.493, 140.862] | 2/3 |
| Unchanged after upgrade | 574.648 | 559.011 | 14.197 [-74.845, 203.283] | 2/3 |

The targeted startup phase does improve consistently: creating-client falls from
2039.606 to1076.430ms, paired saving963.453ms [960.710,970.905],3/3. All3controls
have two failed Info calls and two one-second polling gaps. All3candidates have
two successful Info calls, no application polling gap, and approximately 1.077s
in the first RPC, including transport retry. Total connect improves955.997ms paired median,3/3. These are
measured phase boundaries, not wcprof what-if predictions or a universal2s claim.

There is NO net cold-workflow win across these pairs. B's50.028s run contains a
37.065s Cargo execution. Its timestamped stderr reports30s with zero transfer
while updating the crates.io index, then retries and succeeds. Keep that outlier;
do not subtract the stall from user-visible time. Other image/network/Cargo
variation also remains. Native-normalized cold overhead worsens535.357ms at the
paired median. Candidate cold overhead is still13.509s median.

Warm results are mixed, not proof of a broad readiness benefit. Candidate paired
native overheads remain438.007/646.618/637.555/627.533/432.974ms across the five
warm rows. Library native-normalized overhead worsens8.078ms median; an A library
run median5.184s is retained too. Three pairs do not establish reliable tails.
Every representative scenario remains slower than matched native Cargo.

## Retained non-triggering cohort

The earlier adapter manually created the engine, then inspected its port/identity
before invoking a container:// CLI. All6starts were already ready (39-45ms); there
were no failed Info calls. Cold19649.616->18164.288ms, paired saving1485.329ms2/3,
is NOT a readiness gain: image-envelope variation accounts for much of it while
creating-client improves only0.131ms. Warm paired savings are -6.471/-8.131/
-21.855/-36.095/+7.818ms. That complete cohort remains in manual/, including all
losses. Do not combine cohorts or substitute its cheaper warm lifecycle for the
ordinary image-driver UX.

## Correctness, attribution and remaining work

Original production code fails all3 race-enabled transport-readiness reproductions
at750ms. WaitForReady-only code loses queued and pre-canceled causes in all3
repetitions. After the scoped correction, ^TestWait racecount3 passes in6.054s.
Fixtures include production New/error interceptors, real server status/retry
behavior, custom cancellation/deadline causes and live-context server errors.
See VALIDATION.md, validation/ and the exact build-input hashes.

Each cohort passes36complete maintained wcprof profiles,18cache analyses,
36native/retrieved affected-crate checks and54actual ordinary timed-command
execution audits. Actual bstr version selection, unaffected memchr reuse,
failure/repair/failing revisit and restart reuse remain covered. Each cold consumes
the same full316873658compressed Rust bytes. Cold replay drift is -1.3..-3.7%
for CLI-managed startup and -3.5..-4.5% manually provisioned; warm -0.0..-0.1%.
No precise cold what-if saving is claimed. See gates.json and both result sets.

The new normal-driver breakdown identifies another candidate, not another fix:
Docker's unfiltered container list costs roughly140ms per warm command; start is
only11ms and runtime probing16ms. Investigate limiting the inventory to relevant
engine names while preserving current selection/cleanup/backend semantics. Do
not invent a stale cross-invocation cache or claim all140ms can be removed yet.

## Reproduction and limits

build.sh pins Go1.26.8, the readonly module cache, flags, version stamps and focused
tests. Controllers retain their original owner paths and source/hash guards;
they are exact provenance, not a portable zero-install demo. To reproduce, create
new owners, apply this source change onf7dc, build both CLIs with matching flags,
set the explicit paths/identities before capture, then run run-fullflow.py,
analyze-fullflow.py, audit-ordinary.py, summarize-fullflow.py and phase-summary.py
sequentially in the selected cohort directory. Require all flags/counts in
gates.json, not just analyzer exit0. driver-summary.py is a post-capture derived
analysis; it neither edits traces nor predicts an achieved optimization.

The measured engine is the corrected verified-stream experiment documented by
fork commitb5070c47a345, not pristine main or a shipping containerd replacement.
Its exact image is1fb3565bb5ba on both treatments. Readiness is a CLI-only change;
these timings do not promote the separate engine experiment.

Docker, CLI, engine/native images and local module were preinstalled. Native uses
docker exec in the matching image and follows Dagger initially; host/CDN caches
are not purged. First checks/upgrades are profiled; other timed checks omit
--profile but export local OTLP. Pinned rsync delivery and root-toolchain prep
remain explicit module experiments. Old-engine GC is disabled solely to preserve
unrelated user/build engines. Normal CLI debug is loopback-only: a local static
helper is copied only AFTER the first CLI exits for post-timer diagnostics.
Owned resources were independently verified absent; source hashes and the
retained engine image/container identity were rechecked. Workspaces/logs remain.

No complete-install, artifact export, fmt/Clippy/test-command,
build.rs/features/concurrency, macOS or remote performance claim. No raw telemetry,
private wcprof executable/source, binaries, credentials or OCI images are
published. Full local hashes and capture scope are retained alongside compact
results. No PR or maintainer approval is claimed; the Rust performance goal remains
unmet.
