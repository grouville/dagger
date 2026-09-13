# Current-main CLI readiness reconciliation

Owner: /tmp/dagger-cli-readiness-current.AS6z1ng4.
Base f7dc1f5a418408c3a3e772eeaad31863acd85347, on main7c35.
Readiness behavior reuses old experimental commit
098a09a4b691c5c0d3f530abec6fa1a4ebc5ffbb, not a new discovery.
This CLI base did not contain that change although the measured engine source did.

## Negative gates (terminal)

All commands use Go1.26.8, GOTOOLCHAIN=local GOENV=off GOWORK=off GOPROXY=off
GOSUMDB=off, existing readonly modules and the recorded shared build cache.

1. Original production client SHA256
   0c6e7401dd98cee6e49cb5b8c8c159ff459c549bfdc2971886f2c509688340ec,
   exact old wait_test.go SHA256
   e1e6a39cdb51811482f21c1c7d7e9ea245c4dc1fb1cd9b3e23bb8f40ab85cdf6.
   `go test -mod=readonly -race -count=3 -run '^TestWaitTransportReadiness$' ./internal/buildkit/client`
   fails all3 at750ms, session34613 exit1. before.log SHA256
   ac0691da029191d3c151604fd215546fc8984d0dbba0c79599abc7a2873adda2.

2. WaitForReady-only production client SHA256
   c0cde034117ca59cbb407d732fbc67dcfe33908b7591a2827606434eb4dd0577.
   Additional behavior test SHA256
   ac0289c8053b8ce73b4013c007446f74ecfd3726a65996d10f7885c1d6d7c622.
   `go test -mod=readonly -race -count=3 -run '^TestWait(QueuedContextCause|PreCanceledCause)$' ./internal/buildkit/client`
   loses queued cancel/deadline and pre-cancel causes all3 repetitions,
   session86263 independently polled terminal1. cause-before.log SHA256
   5837f121de115350e31974897143028c1886bcc1eaccbe8ecedd3e6519572148.

Next change only normalizes Canceled/DeadlineExceeded when the local context is
done; server-returned statuses with a live context remain untouched. The old
pre-cancel test now asserts local errors.Is identity rather than a gRPC wrapper.
Global gRPC backoff and application-Unavailable one-second retry are unchanged.

## Positive gate and build

`go test -mod=readonly -race -count=3 -run '^TestWait' ./internal/buildkit/client`
PASS6.054s. Build97876 terminal0; matching control flags/toolchain, no dependency
updates. Candidate d4eb2c81edc8c04a9512d276dce1346f73e45dbc608e9812662623b90e694f86.
build-inputs.sha256 SHA25628a1d8f7293394b73ab13776dbbb14bb5bfbe4f0a9f9585f3f9606c1d8c9f6a3.
after.log SHA256076700faf4dd4208ee2c78b7ab8d28b93b34be1dd43d472cdb50058ebe244586.
Upstream main reverified7c35 with ls-remote session65798 terminal0.

Independent read-only review found no required source/test correction. Important
behavior boundary: queued transports now follow configured gRPC reconnection
backoff without the previous periodic application ResetConnectBackoff. Global
configuration is unchanged, but persistent-outage retry timing is not identical.

## First fullflow: valid, no readiness trigger

Fullflow5355 terminal0, cohort/tmp/dagger-rust-cli-readiness-ab-f1efly5c.
Analyzer8344 and ordinary93734 terminal0. All36complete profiles,18cache,
36native/retrievedcrate and54ordinary timed-command audits PASS. Phase/summary
gates PASS. Allsix starts connected without transport failure: creatingclient
39-45ms, no1s polling gaps. The actual readiness race was not exercised here.

Cold A19649.616->B18164.288ms, paired saving1485.329ms2/3, but paired image
envelope saving2255.646ms and creating-client saving only0.131ms. This is NOT
an attributable readiness speedup. Keep warm losses: exact-6.471,app-8.131,
library-21.855,upgrade-36.095ms paired CLI savings; followup+7.818ms.
Candidate overheads remain292.695/507.235/507.899/454.891/279.523ms.

Cold replay drift-3.5..-4.5%, warm-0.0..-0.1%; no exact cold what-if claim.
Same316873658full compressed bytes and stream overlap in both treatments.
Allsix owned engine/cache groups independently absent after cleanup;
retained8ad9ac/image1fb356 unchanged. Build-source hashes rechecked.
Raw42601589 SHA49a0926c992137ed9faaf698ddf7b128a52f09e2a1cef45d204801630b55e57a.
Summary SHA2cacc1808198dfc29e8e3f1785df27201595597f129eacca4867c4477ab35a4c.
Phases SHA3971a7310af9d4f96d68d7961beae70456ecb635430a1d3e390e46bc1e857634.
Report SHA63155b599a1323c8d5a0e4f1236f4ffe363e8fe0dd74f02808bcc761a49c7a83.
Ordinary SHAbdf19b5713d17ee55dfa8d8c7d173d12d79cfda88da81b3867fbf7d37c01fe86.

This adapter manually provisions the engine then inspects its debug port and
identity before starting the CLI. That is an explicit benchmark lifecycle, not
the default CLI-managed provisioning path. Preserve it; next use a new owner
and adapter where the standalone CLI itself provisions the exact preinstalled
engine image, with no artificial readiness delay and the same full Rust matrix.
No new source/CLI change and no readiness win promoted or pushed yet.
