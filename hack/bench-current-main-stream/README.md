# Current-main verified image streaming: default-route cold comparison

This branch preserves a measured experiment and a reproduced dependency cleanup
fix. Normal builds of the branch are unchanged: engine and containerd changes are
inert patches, not a shipping default or maintainer-approved design. It is based
on Dagger 503d3410ef3d, which contains upstream main 7c35e6274737, independently
reverified before timing. No lazy snapshotter, listener, public OCI upload, or
Cargo execution on an unverified filesystem is involved.

## Result

Six fresh independent engine/Cargo states in AB/BA/AB order, using the same
published CLI f7dc1f5a4184 on both sides and the unchanged official gzip Rust
image through the engine's normal packaged registry configuration. There is no
direct-origin override or prepopulated local registry in this comparison.

Times are milliseconds; positive paired savings favor B. Within-run warm repeats
are summarized before pairing, not treated as nine independent engine pairs.

| Flow | A median | B median | Paired saving median [min, max] | Favorable | B paired native overhead |
|---|---:|---:|---:|---:|---:|
| First check, profiled | 29657.039 | 25122.968 | 4534.071 [3612.302, 5732.778] | 3/3 | +18146.655 |
| Provision + first check, profiled | 29881.425 | 25999.643 | 3881.782 [3607.095, 5683.175] | 3/3 | +19023.330 |
| Exact check | 415.480 | 415.246 | -1.474 [-3.133, 20.259] | 1/3 | +295.383 |
| Application edit | 795.687 | 793.919 | 0.934 [-8.430, 12.363] | 2/3 | +497.231 |
| Workspace-library edit | 965.979 | 945.530 | 15.335 [4.772, 30.207] | 3/3 | +497.963 |
| bstr 1.12.0 -> 1.13.0, profiled | 2152.287 | 2092.688 | 68.989 [-56.768, 169.478] | 2/3 | +454.895 |
| Unchanged after upgrade | 416.602 | 415.135 | 13.197 [-24.523, 102.601] | 2/3 | +284.335 |

The cold image-delivery envelope saves 3711.386 ms at the paired median,
range 3527.852–4206.496, 3/3 wins. Native-normalized first-check overhead improves
3748.978 ms median, also 3/3. Candidate first checks range 18.533–26.443 seconds;
all points and losses remain in results.json. Three pairs do not establish tails
or a universal registry/network result. Provision-inclusive overhead remains
19.023 seconds median: the goal is very far from met, not a native-parity claim.

Warm results are mixed. Exact-hit native overhead worsens 3.284 ms at the paired
median in all 3 pairs; application overhead improves only 2.918 ms. The library's
15.335 ms CLI saving shrinks to 3.655 ms after native normalization. Do not claim
this cold-image treatment solves warm module/session latency. This engine lacks
the separate parser-statistics prototype used in the earlier retained-engine CLI
pilot; its absolute warm times are not an A/B of that pilot's 0.377 s exact result.

See results.json and phases.json for every sample, paired overhead, ratios and
phase boundaries. Do not add these gains to mirror-policy, codec or CLI cohorts.

## Mechanism and correctness

The combined treatment includes ordered verified-layer import, bounded hashing,
operation-lease/reuse prerequisites, private final-layer streaming and reader
lifecycle changes. It does not isolate each component's performance contribution.
The largest layer is consumed before its own download completes in all 3 B runs;
no such overlap occurs in A. Every cold run downloads and consumes the same full
316873658 compressed bytes. Dagger publishes only after compressed verification,
calculated diffID verification and source labeling succeed. Existing leases,
snapshots and immutable result ownership are retained.

An earlier current-main candidate failed a real Zstd early-error fixture. A gated
schedule makes that failure deterministic: the default async decoder blocks on
more input before invalid-tar extraction enters cleanup. All 10 race-enabled
before runs hit the gates then fail at 5 s; all 10 after runs pass. Only apply.go
differs between those negative and positive sources: close input before joining
the last successfully initialized processor, retaining that processor if later
initialization fails. No decoder-concurrency or digest-verification workaround.
The unsuccessful build and original captures remain retained; they were not timed.

close-order-only.patch isolates that correction from the already combined prior
candidate. Reverse it after applying containerd.patch to reconstruct the failing
production source; reapply it for the passing source. The gated fixture stays
identical. close-order-validation.json retains the exact command and file hashes;
the inner integration fixture requests ten race-enabled repetitions. The source
verifier also checks both reconstructed dependency hashes.

The corrected source passed the supported snapshot race selection (63 tests),
real gzip and Zstd race fixtures, engine build and query smoke check. Borrowed
reader tests passed 3 race repetitions in 1.054 s. All 36 complete wcprof profiles,
18 cache analyses, 36 native/retrieved affected-crate audits and 54 actual ordinary
timed-command execution audits pass. Actual bstr version selection, unaffected
memchr reuse, failure/repair/failing-source revisit and restart reuse are covered.
Warm replay drift is -0.0% to -0.1%; cold drift is -2.3% to -3.7%, so cold what-if
predictions are not precise measured savings.

All six disposable runtime/cache groups were independently verified absent after
the run; both retained build-engine identities were unchanged. The receiver exited
normally and is absent. Source/controller hashes were rechecked after timing.

## Reproduction and review boundaries

engine.patch applies to the recorded Dagger parent. containerd.patch applies to
stock containerd v2.2.5, not an already patched dependency. Both include the exact
tested fixtures. source-manifest.json records all 26 changed-file hashes. Validate
reconstruction without altering either source checkout:

```sh
python3 hack/bench-current-main-stream/verify-patches.py \
  --control-dagger /path/to/dagger503d \
  --control-containerd /path/to/stock-containerd-v2.2.5
```

To build the experiment, use new disposable full checkouts, apply each patch at
its own root, and stage the dependency under the supported engine-dev source
allowlist with a temporary local replacement. The recorded build/test controllers
pin all inputs and give the exact supported commands. The replacement is NOT a
shipping dependency strategy: containerd changes need upstream review/release and
a normal Dagger dependency update. See UPSTREAM-SPLIT.md for independent fixes,
compatibility gating, fallback, Windows-layer and concurrency limitations.

Frozen controllers in this directory retain their original owner paths and
identity guards. They are provenance, not a portable zero-install demo. To repeat,
create new owners, rebuild both images and the pinned CLI, update only explicit
path/build identities before capture, then run sequentially:

```sh
python3 run-fullflow.py --execute
python3 analyze-fullflow.py /tmp/NEW-COHORT
python3 audit-ordinary.py /tmp/NEW-COHORT
python3 summarize-fullflow.py /tmp/NEW-COHORT
python3 phase-summary.py /tmp/NEW-COHORT
```

The analyzer's zero exit alone is insufficient: require all_captures_pass=true,
all 54 ordinary audits and the stream-overlap gate. No raw telemetry, private wcprof
binary/source, native profiles, credentials or engine images are published.

Docker, CLI, engine images, local module and native Rust image were preinstalled.
Native Cargo uses docker exec in the matched image and follows Dagger initially;
host/CDN caches are not purged. First checks/upgrades include profiling; other
timed checks omit --profile but export local OTLP. Pinned Debian rsync delivery
and root-toolchain preparation remain explicit module experiments. This is not
full installation, every Rust project, artifact export, fmt/Clippy/test-command,
build.rs/features/concurrency, macOS or remote-engine performance validation.

## Next measured bottleneck

Some cold traces show two Unavailable Info calls followed by one-second sleeps
inside client readiness. This is directly visible, not a cold-image saving:
one pair includes an additional 2.073 s control connect cost. The separate shared
image envelope still improves in every pair. Investigate readiness with a focused
transport/socket repro and explicit cancellation/error semantics before a fix;
do not simply lower global remote retry delays or predict a universal2s gain.
