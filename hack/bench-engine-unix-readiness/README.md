# Wait for the Unix engine socket inside the connection budget

Measured cold improvement, with unresolved warm regressions. This is a reviewable
experiment checkpoint, not a claim that the Rust performance goal is achieved.

## Change and compatibility

`buildctl dial-stdio` can start before the engine binds its socket. Previously
ENOENT/ECONNREFUSED ended the helper immediately despite a positive connection
timeout, forcing the client transport to reconnect. The preceding CLI readiness
change wakes queued Info requests, but cannot prevent that transport backoff.

For positive timeouts, the helper now retries only those two socket errors with
one fixed net.Dialer deadline. Delays begin at 5ms and grow to at most 50ms,
bounded by the remaining budget. A final dial returns the standard timeout error
with its Unix address and net.Error/os.IsTimeout classification. No custom error
type, global gRPC retry change, listener, session/cache bypass or egraph change.

Zero/negative timeouts and permanent errors keep the original behavior. Successful
connections retain the original stream and half-close handling; the connection
deadline does not become a read/write deadline. Permanently wrong/missing sockets
now wait up to the positive timeout (default five seconds), instead of failing
immediately. The final timeout diagnostic does not retain the last transient errno.

The host connection owns closing its subprocess, not the constructor context.
Real Docker exec validation confirms that local closure can return promptly while
the remote helper survives until its bounded timeout. This does not implement or
claim immediate cancellation forwarding into Docker exec.

## Matched full-flow result

Same CLI 6a5 (published inventory stack 40ad085a), unchanged module, official gzip
Rust image, flags, registry route and verified-stream implementation on both
sides. A is engine 1fb356; B is engine 5d6602 and changes only this helper plus two
test files. Both source trees include upstream 7c35e627, reverified before building.
The separate verified-stream/containerd experiment remains held fixed; normal
builds of this CLI-stack branch do not activate that separate image treatment.

Six fresh engine/Cargo states in AB/BA/AB order. The ordinary CLI provisions each
engine inside the first-check timer; every warm command keeps normal image-driver
discovery/start. No manual listener. Three within-run repeats are summarized
before calculating three independent pairs, not nine independent observations.

Milliseconds; positive paired saving favors B. Separate medians do not subtract
to the paired median. First check already includes provisioning, not an additive
second row. All losses and native comparisons remain in results.json.

| Flow | A median | B median | Paired saving [min,max] | Favorable | B paired native overhead |
|---|---:|---:|---:|---:|---:|
| Provision + first check, profiled | 19917.309 | 19347.752 | 1597.428 [263.739,2630.597] | 3/3 | +12642.153 |
| Exact check | 510.945 | 529.061 | -11.575 [-32.098,3.234] | 1/3 | +409.015 |
| Application edit | 898.174 | 886.298 | 10.683 [-23.446,26.979] | 2/3 | +595.259 |
| Workspace-library edit | 1066.299 | 1068.160 | -15.489 [-49.195,40.885] | 1/3 | +606.818 |
| bstr 1.12 -> 1.13, profiled | 2188.572 | 2273.383 | -86.506 [-95.612,-59.959] | 0/3 | +529.586 |
| Unchanged after upgrade | 538.308 | 514.936 | 21.253 [3.202,45.750] | 3/3 | +371.792 |

The targeted cold readiness boundary improves from 1082.596 to 117.711ms at the
separate medians; paired saving 954.667ms, all 3 pairs. Overall connect saves
1016.773ms paired, all 3. Image delivery also varies favorably at the paired median
by 512.325ms; do not attribute the full 1.597s cold-flow saving to socket readiness.
Candidate cold runs range 18.320–19.358s. Three pairs do not establish reliable tails.

Native-normalized cold overhead improves 1072.023ms at the paired median, but only
2/3 pairs. Keep the 0-A native 12.827s outlier: its Cargo log reports 6.62s for Cargo
itself and also records rustup channel/component setup. The unprofiled native
record does not resolve the remaining time among rustup, runtime and scheduling;
do not invent a precise cause or remove this observation.

## Warm and restart limitations: not a non-regression claim

Post-capture diagnostics inspect the already accepted traces without changing
timings, source or raw records. All 60 headline warm traces retain two successful
Info calls, but connection latency also increases in some scenarios:

| Flow | Paired full-command saving | Paired connect saving | Paired first-Info saving |
|---|---:|---:|---:|
| Exact | -11.575 | -24.656 | -14.066 |
| Application edit | 10.683 | -1.952 | 2.615 |
| Library edit | -15.489 | -2.067 | -4.647 |
| Dependency upgrade | -86.506 | -30.547 | -16.147 |

Upgrade first-Info is slower in every pair. Its Cargo-action and pre-root costs
also increase, and native is slower on B in every pair, but native normalization
does not erase the connection losses. These phase medians are not additive.
The traces lack helper retry-count/errno events; they cannot establish whether
small helper waits caused these changes. A tighter ready-socket comparison is a
follow-up, not a completed non-regression proof.

Separate diagnostic restart checks (not ordinary edit timings):

| Run | First Info | Full command |
|---|---:|---:|
| 0-A | 1079.931 | 1971.685 |
| 1-B | 215.063 | 1076.523 |
| 2-B | 8634.305 | 9477.710 |
| 3-A | 1078.951 | 1979.835 |
| 4-A | 1084.622 | 1980.610 |
| 5-B | 261.445 | 1148.995 |

The 2-B engine log starts initialization at 05:49:39Z but advertises its socket
listeners only at 05:49:47Z. First Info spans05:49:39.360775–05:49:47.995080Z.
Engine initialization occupies most of this interval; it is not evidence of
8.6s polling against an already-listening server. Whether a helper timeout plus
transport retry contributed is unproven. The outlier and unresolved startup
tail remain in warm-phases.json; no restart-tail improvement is claimed.

## Correctness and reproduction

The original real delayed-listener repro fails missing/refused sockets in all
three repetitions against unchanged production. Local after-tests pass three
race repetitions in 6.633s. Review then bounds a test read without masking its
deadline property and shortens owned socket fixture paths for Unix address
limits; this is not macOS runtime validation.

The final fixture passes the supported engine-dev race/count3 selection (27
reported passes), engine build and smoke query. The publication checkout
independently passes three race repetitions in 6.603s. Focused reproduction with
the repository's Go toolchain:

```sh
go test -mod=readonly -race -count=3 -timeout=90s -run '^TestDial' ./cmd/dialstdio
```

For the negative case, apply only the test files to this commit's parent and run
`TestDialerWaitsForUnixSocket`; the production retry must be absent. Tests cover
missing/refused startup, one timeout budget, invalid/permanent/nonpositive
behavior, established-stream lifetime, both half-close orders, constructor
context detachment and connection-owned child closure/reaping.

Real Docker checks on the uniquely owned candidate: a 1s absent-socket budget
exits in 1007.9ms; closing the local client returns in 3.18ms, while its remote helper
remains and is observed gone by 5184ms under the original 5s budget (including
poll/exec observation). Those are lifecycle checks, not Rust performance scores.

All 36 complete maintained wcprof captures,18 cache analyses,36 native/retrieved
crate comparisons and54 actual ordinary-command execution audits pass. Actual
bstr selection, unaffected memchr reuse, compile failure/repair/failing-source
revisit, restart reuse and all 316873658 compressed Rust bytes are checked.
Warm replay drift is -0.0..-0.1%; cold -3.7..-4.7%. No precise cold what-if claim.
All 2922 recorded source/tool/controller inputs were rechecked after timing.

Frozen controllers retain owner paths and hash guards: they are provenance,
not a portable zero-install demo. New full comparisons require fresh owners,
identical CLI builds, the recorded base stream experiment and only the helper
change, new owned engine identities, and updated explicit manifests before
capture. Run build-candidate, Docker lifecycle, run-fullflow, analyze-fullflow,
audit-ordinary, summarize-fullflow and phase-summary sequentially. Require every
gate/count, not only exit 0. warm-phases is explicitly a post-capture diagnostic.

Docker/CLI/engine/native images and module were preinstalled; native Cargo uses
docker exec. Root-toolchain component setup remains included. Host/CDN caches
are not purged. First checks/upgrades include profiling; other timed scenarios
omit --profile but export local OTLP. Old-engine GC is disabled only to preserve
unrelated user/build engines. The59-container unrelated inventory stayed stable.

All six disposable engine/Cargo groups were cleaned and independently absent;
the receiver exited and both retained build-engine identities were unchanged.
Source, outputs and evidence remain local. No raw telemetry, private analyzer,
binaries, unrelated inventory names or OCI images are published. No PR or
maintainer approval. No complete-install, artifact/fmt/Clippy/test-command,
build.rs/features/concurrency, macOS or remote performance claim.
