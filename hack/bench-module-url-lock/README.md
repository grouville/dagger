# Persist successful module URL routing through the workspace lock

Status: focused correctness checks passed; the repeated URL probe is removed
and warm CLI pilots improved. This is not Cargo parity or a cold-start win.

## Stack and review scope

| Branch | Parent | Validated scope |
|---|---|---|
| `perf/rust-23-telemetry-completion` | Upstream `7c35e6274737acff0f6bd76614abb5e04efa7d12` | Main-session telemetry completion; no demonstrated Rust speedup |
| `perf/rust-24-module-url-lock` | `perf/rust-23-telemetry-completion`, `bbd67d9db2edd6123bcca4fd1091a579e5523e37` | This URL-lock change; focused race/integration tests and two complete CLI captures |

Upstream main was rechecked before publication and still pointed at `7c35e627`.
The code change is independently reviewable: three production files and two
test files. The stack parent supplies reliable final wcprof telemetry. Neither
branch activates the separate verified-image-stream/Unix-readiness prototype.
No maintainer approval is implied. Earlier `experiment/` branches are preserved.

## Context and fix

Every fresh CLI session probes an eligible remote module URL with `dagger-get`.
Positive redirects already use `dagger.lock`, but an HTTP 200 falls back to the
original URL and is only remembered within the session. Ordinary repeated
commands therefore repeat a network round trip even when all build results hit.

Record confirmed HTTP-200 routing identities using the existing session-owned
workspace lookup setter and shutdown export. The new `vanity-url-resolution`
operation distinguishes identity-capable readers from older redirect-only
readers. A self-value returns the original reference verbatim, preserving
schemeless transport selection and `#ref:subpath` versus `@version` syntax.

- Legacy `vanity-url` entries remain authoritative. Explicit update refreshes
  that mapping once and synchronizes a coexisting shadow entry.
- Explicit update can refresh an identity or discover a redirect. Unsuccessful
  refresh preserves the old pin; an absent redirect does not silently undo a
  previously pinned positive mapping.
- Failed requests, cancellation and ignored redirects remain session-local.
  Userinfo/query-bearing URLs do not create new persistent identity entries.
- This is URL routing, **not** Git visibility or authorization. Those checks
  still execute. There is no global cache, TTL, listener, credential shortcut,
  synthetic profile marker or new egraph/resource-ownership mechanism.

Routing is pinned until explicit `dagger workspace update`, like other recorded
lookups. Older engines preserve but ignore the new operation; they may probe
again and discover different routing. This is format compatibility, not a
promise of identical cross-version routing behavior.

## Correctness reproduction

From this branch with its Go toolchain:

```sh
go test -mod=readonly -race -count=3 -timeout=90s \
  -run '^(TestDaggerGet|TestResolveDaggerGet|TestSourceURLWithVersion|TestUpdateVanityURL|TestVanityURLResolution|TestUpdateWorkspaceLockIgnoresUnsupported)' ./core

dagger api call engine-dev test --pkg=./core/integration \
  --run='^TestLockfile$/^Test(VanityIdentityPersistsAcrossSessions|DefaultRemoteCommitDoesNotMutateLock|DefaultModuleCall|SchemelessRemoteIgnoresLockedTransport|GitLatestPinnedHTTPSUnavailableRemoteUsesPin)$' \
  --parallel=1 --timeout=15m --count=1 --test-verbose=true
```

Executed on main plus perf23 with exactly this branch's five code/test files:

- Focused race/count 3: pass, 2.485s package test runtime, not build wall time.
- Supported source-built integration: all five selected methods pass; raw
  telemetry independently identifies their final continuations and suite pass.
  Go test runtime 34.709s; full runner/build/provisioning invocation 383.381s.
- The successful integration command also renders its bound dev-engine service
  as `ERROR` at teardown. That artifact is retained; this is not a claim of a
  clean overall service teardown or a diagnosed cause.
- Separate unchanged-main old-reader tests previously passed race/count 3:
  generic parse/serialize/update preserve unknown entries; old resolution
  ignores them and respects legacy positives. This checks main `7c35e627`,
  not every historical release binary.

The real CLI test starts without a lock, verifies automatic session-delta export,
then checks replay from a second process and explicit update. It does not count
network requests; avoided-probe counts are asserted by the unit tests.

## Ordinary CLI performance

Two complete captures on **one retained engine pair**, with the same CLI and
already-public pinned remote Rust module. Each capture uses fresh, independent
source/Cargo/registry/XDG namespaces and new application edits. Six alternating
AB/BA exact cycles and three matched edit cycles per capture, plus setup,
profile companions, deliberate failure and repair. No tests, builds or
checkouts overlapped either timing run. All 56 observations are retained in
[results.csv](results.csv), including unfavorable samples.

Each capture passes 28 actual-command checks and 16 maintained wcprof
completeness gates: **56/56 and 32/32 overall**. Declared and received engine
span counts match exactly; no dropped/unfinished spans were accepted. Warm
profile replay drift is 0.0 to -0.1%. The first capture's B provisioning profile
has -4.3% replay drift, retained and not used to claim a cold improvement.
Actual application edits execute Cargo and rebuild only ripgrep 15.2.0; both
primes select bstr 1.12.0 with the same package/version set. Deliberate compiler
errors execute Cargo and exit 101; repair succeeds. No stale result is accepted.

Milliseconds. Paired medians need not equal differences of marginal medians.
These are within-pair observations, not independent engine replications or
statistical evidence of general speedups across machines/projects.

| Capture / flow | A median [min,max] | B median [min,max] | Paired saving [min,max] | Favorable |
|---|---:|---:|---:|---:|
| 1 / exact cached check |861.217 [823.514,961.182]|785.766 [755.750,837.370]|96.622 [-0.872,124.056]|5/6|
| 2 / exact cached check |772.975 [716.854,921.038]|637.993 [597.298,840.940]|123.392 [39.566,152.676]|6/6|
| 1 / application edit |1104.154 [1091.145,1104.923]|992.861 [952.519,1131.364]|98.284 [-26.441,151.634]|2/3|
| 2 / application edit |1214.139 [1139.477,1238.264]|1173.625 [1014.145,1426.007]|64.640 [-211.868,125.332]|2/3|

Exact headline commands omit `--profile`. Application/failure/repair and
separate exact companions use it; all commands export local telemetry. DNT is
enabled, no external exporter is configured, and the image+Docker URI uses
`cleanup=false` to protect unrelated engines. Complete CLI startup, session and
shutdown remain timed; there is no resident/listener fast path.

Mechanism: exact companion `parseRefString` goes from 66.025/73.327ms to
0.511/0.464ms. Git visibility still takes 96–542ms in the repeat's application
samples. The 211.868ms unfavorable pair includes B visibility 542.454ms versus
A 238.676ms; it is not discarded. The entire paired CLI saving cannot be
attributed to the roughly 66–73ms avoided probe: other intervals vary too.

Failure/repair, one sample per arm per capture: A/B are 1256.028/1113.043 and
938.170/847.893ms in capture 1; 1014.821/980.110 and 640.212/651.684ms in capture 2.

### Setup and remaining gaps

First module observations were **66.964/71.942s** in capture 1 and 1.228/0.806s
in capture 2. The module is a subdirectory of an existing large fork monorepo;
repository delivery is a separate onboarding problem, not a benefit of this
patch. First Cargo checks were 7.590/16.748s and 7.520/7.136s. The retained
engines have different image/Git histories: none of these are matched cold
comparisons, and the repeat's cached Git/image state is not first-install UX.

Correctness is tested on main plus perf23. Performance arms additionally inherit
the same separate stream/Unix prototype at parent `503d3410`; frozen manifests
prove only these five URL-lock paths differ. This is **not** clean main versus
a checkout of the entire published stack. No new native Cargo, full matrix,
workspace/external-dependency invalidation, artifact export, full installation,
macOS, remote-engine or concurrency performance claim. The fixture's pinned
source-sync packages target Debian bookworm/amd64, not a universal Rust module.
The original cold and Rust edit-loop goals remain unmet.

## Workload and retained reproduction

Use ripgrep commit `3fce3b5bb0236da2df6d99672afb8a719642eca7`, the
[published benchmark fixtures](https://github.com/grouville/dagger/tree/b5070c47a3458a535294d13a212f2cd2d221c757/hack/bench-rust-loop)
(`ripgrep-bstr-1.12.0.patch` and `rust-toolchain-rustfmt.toml`), and this workspace
configuration, with a fresh distinct cache key in each arm/capture:

```toml
[modules.rust]
source = "https://github.com/grouville/dagger#b5070c47a3458a535294d13a212f2cd2d221c757:hack/bench-rust-loop/module"
[modules.rust.settings]
image = "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b"
cacheKey = "replace-with-new-capture-and-arm-key"
pinnedSourceSync = true
prepareProjectToolchain = true
```

Start without `dagger.lock`. Run `dagger --profile check --list rust:check`,
then `dagger --profile check rust:check`; retain both setup times. Alternate six
ordinary `dagger check rust:check` pairs, then capture one profiled exact pair.
For each of three edit pairs, change the version string in
`crates/core/flags/doc/version.rs` to a new identical string in both workspaces
and run `dagger --profile check rust:check`. Finally add an explicit
`compile_error!` and check exit 101, then restore the prior good edit and check
success. Never manually seed the lock or reuse a capture's Cargo namespaces.

Frozen local owner: `/tmp/dagger-url-lock-perf.V27shQTb`. The exact controllers
are `pilot/capture.py` and `pilot-r2/capture.py`: `--preflight`, `--execute`, then
the adjacent `analyze.py`. They refuse overwrites and validate source hashes,
engine identities, configuration, lock transitions, selected packages and
maintained-profile completeness. The local reports preserve every command and
input edit. Reproduction needs a fresh owner/namespace and reviewed actual
engine identities; these are not portable benchmark scores from arbitrary CLIs.

- CLI SHA256: `6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad`.
- A image: `sha256:1cc1d7e14f1facf8aa9dde08750083701f33e02281cf206b13a3235361263b67`.
- B image: `sha256:915748ca80a3b9efaf1e99bb2e47c45ef637784772908116a869a2d41e56348f`.
- Build receipt: `99dca933eafcec5d92465197b7177137a08e62426e29cba61b9d912fdb4843aa`.
- Supported-test receipt: `faf43de27214657ae1f35f0995d554a8a8038736acc5c66df7ca0d53380df943`.
- Capture controller (same bytes both captures): `2068ccb76a4df27245586304d774eef83ee391dafbc9d5feb839fdf153e58bc0`.
- Audit controller: `6cee40d76ad870522813a7ddb9126ef1734bf30ec95637052fac7ea360788697`.
- Report 1: `15cbfcd1e3ca9f063c40577b1cc53a67574e71fbd91b18fab1b947ab284689f7`.
- Report 2: `d0532f69d592b7c8c3ff975ba8752395e644710996b1c110d6cf3b31b98c1bd5`.
- Raw 1: `163e47731376433fa2e0e8537f587e574cf97875be7f52a09a8bd9c11c122c4e`.
- Raw 2: `233af70cd2ab0dacd4fa3955f710643b13533ebc5adef6601ec6940a05157de8`.

Only code, tests and explanatory summaries are published. Raw telemetry,
binaries and the private maintained wcprof executable remain local. No PR.
