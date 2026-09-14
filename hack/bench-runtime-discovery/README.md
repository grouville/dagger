# Runtime discovery: attribution, lifecycle caveat, rejected start-skip

2026-09-14. **Diagnostic checkpoint, no activated runtime change or new CLI
speedup.** The Rust goal remains unmet. The prototype below is intentionally
rejected; production sources were restored to parent
`2fb4cf8e14f0cce07e080717a2a93911c4ea57bc`, based on upstream c305ed37.

## Why this boundary

The retained ordinary-process exact-check wcprof has 153 operations, no open or
dropped events and -0.1% replay drift. It attributes 83.7ms to filtered Docker
inventory, 16.8ms to availability and 11.1ms to `docker start`. Those are measured
span times, not independent guaranteed CLI savings. Source/engine identities
remain those of the [relay cohort](../bench-rust-toolchain-packaging/RELAY.md).

Docker name prefiltering was already tested and is already in that cohort's
CLI6a5. Its historical 20-pair probe saved51.134ms on a58-container host, but
filtered inventory still cost84.923ms. It is not a new discovery here. Current
main's backend is unfiltered; do not compare different CLI compositions and
attribute all differences to a new start-state change.

## Read-only attribution

Eight alternating forward/reverse cycles on the same local Docker daemon,
69 total containers and six selected engines. All selections agree; full
inventory names are unchanged before/after. Container identity stability was
not checked. No containers are created, started,
stopped, executed into, removed or reconfigured by [probe.py](probe.py).
All48 observations are in [samples.csv](samples.csv).

| Operation | Median ms | Min–max ms | Samples |
| --- | ---: | ---: | ---: |
| Formatted Docker client/server version | 15.820 | 15.480–16.572 | 8 |
| Unfiltered names | 140.621 | 137.095–145.321 | 8 |
| Filtered names | 83.852 | 81.340–86.426 | 8 |
| Same filter, names + state | 84.064 | 80.510–91.569 | 8 |
| Exact target inspect | 12.207 | 11.443–12.822 | 8 |
| Same filtered list over local HTTP API | 71.701 | 68.991–72.622 | 8 |

The HTTP measurement includes a fresh Unix-socket request, response and JSON
decoding, not pure daemon CPU. It deliberately bypasses Docker CLI context,
authentication and plugin setup for attribution only; it is not a compatible
replacement implementation. The version probe uses formatted output rather
than the driver's full `docker version`. Adding state has no material measured
listing cost here; replacing the entire Docker CLI would not remove most of
this listing latency. These are not Rust flow measurements or a new wcprof run.

## Important full-flow scope correction

Both the earlier packaging and relay harnesses set `cleanup=false` in the engine
URL **and** `DAGGER_LEAVE_OLD_ENGINE=1` to protect unrelated user/build engines.
They use ordinary standalone CLI processes and new sessions, not `listen`, but
they exclude automatic old-engine removals while still listing retained engines.
Thus their tables do **not** fully validate default-cleanup UX or a normal
one-engine installation. The code already recorded this safety choice; the
published scorecards now make its measurement consequence explicit.

The current discovery probe is also on a retained multi-engine host. Its cost
cannot be subtracted from old timings to manufacture a clean-host result.
Neither the performance impact nor a default-cleanup A/B is established here.
Use an isolated runtime for that test; never enable cleanup on this host in a
way that would remove the user's retained engines. Garbage collection stays a
required part of the actual user-flow goal.

## Candidate and deterministic rejection

The inert [rejected patch](rejected-running-state.patch) returns running state
with the existing list result and skips `ContainerStart` only for positively
running Docker targets. Metadata is invocation-local, not a persistent cache.
Unknown/stopped states still start; Apple keeps its separate pre-start safeguard;
Podman/nerdctl/Finch commands are unchanged. GC selection and execution remain.

Initial focused tests passed three race repetitions:45 root executions plus54
nested cases, no failures/skips (package1.084s). Gates cover custom targets,
cleanup enabled/disabled, preserved names, start errors, cancellation, stale
state across separate calls and backend command compatibility. Passing these
tests alone did not justify adoption.

Review found a widened existing stop-before-connect window. A deterministic
fake returns a running snapshot, then stops its backend before returning the
list response. The former unconditional start recovers this ordering; skipping
start does not. `TestImageDriverCreateRecoversStopDuringListing` fails3/3 for
the candidate. A control overlay making only that start guard unconditional
passes3/3 under race (package1.032s). The control retains the metadata API to
isolate the decision; it is not a separately built stock CLI.

The connector retries `docker exec`, not provisioning. Current
`engine/client/buildkit.go` permits readiness retries for up to10 minutes;
`commandconn.New` returns after process launch, before Docker exec success.
A fallback handling only synchronous Connect errors would be insufficient.
**No actual ten-minute hang was run or measured.** The fixture proves the
changed stop-before-start ordering, not the complete real-runtime race matrix.

Disposition: reject this prototype; do not add substantial retry/lifecycle
machinery for an unproven11ms opportunity. The approximately11ms is the earlier
start span, not a measured saving. All production/test edits were reverted
using exact-source restoration; only this inactive patch/evidence is published.
No engine build or full CLI benchmark was spent promoting a failing candidate.

## Reproduction and receipts

The read-only controller has the original retained target name and local
`/var/run/docker.sock` path. Copy it to a fresh writable owner, explicitly adapt
the target to an existing engine, and run `python3 probe.py`. It refuses an
existing `run/` output directory. It queries the daemon's API version and never
records full inspect/environment/authentication data. This is a local Unix
diagnostic, not validation of remote Docker contexts or other platforms.

For the rejected prototype, use an **owned scratch checkout** of parent2fb4cf8,
apply the patch and run with pinned Go1.26.8:

```sh
go test -mod=readonly -p=2 -race -count=3 -run '^TestImageDriverCreateRecoversStopDuringListing$' ./engine/client/drivers
```

Failure is expected. To isolate the decision, restore only the unconditional
start guard in that scratch copy and rerun: all three cases should pass. Do
not apply this inactive patch to a working engine as a recommended fix. The
patch applies cleanly with `git apply --check --whitespace=error` at its pinned
parent. Staged whitespace checking excludes the patch file itself: its frozen
unified-diff context prefixes intentionally include spaces before Go tabs.
Full controller, source overlay,
logs and earlier passing suite remain local:
`/tmp/dagger-runtime-discovery.yBs9Zfpi`.

| Receipt | SHA256 |
| --- | --- |
| Probe summary | 3a827679cbfccf452aab22014e99057e14a3f9e5e5b113ebd0b682a547773b78 |
| Probe raw rows | ff51550b86d2f92dd49b00eb1b6988ecaa946517fff160b3f3f15b59d2ba72e0 |
| Candidate patch | 888f247ad42feb9af2dce20401cc10ec7b9795bfff6e9289773a47d118cfb27a |
| Initial passing tests | 3160cec2f829ad9e6ab75e651a8140c45da355c429e90aa95eaa04112e3a5e4d |
| Candidate race failure | 776317ed38470d9b5b0f9457f4fbd80effd312a920b185bef84645bdebed7596 |
| Unconditional-start control pass | 4ef5b17143c04427e111ff96c67cd8fd71a7ba76ef3357889e0fa7dfe5785322 |

No raw profiles, private analyzer, binaries, credentials, public images or PR
are published. No kernel/security/cache setting changed and no sudo was used.
