# Filter Docker inventory before preparing unrelated container summaries

This CLI-only change preserves the existing engine-selection and cleanup
predicate: names beginning with `dagger-engine-`, or the exact requested custom
container name. It passes those alternatives to Docker's name filter, keeping
the common Go postfilter authoritative. No persistent inventory cache, listener,
session/egraph bypass, or engine image change is introduced.

The internal backend API gains optional prefilter hints; an empty hint still
lists everything. Only the `docker` command translates them into a regular
expression. Podman, nerdctl, Finch and Apple keep their existing commands.
Names are quoted, exact alternatives anchored, stopped containers included,
and an optional leading slash handles Docker's internal names. Backend results
may overmatch aliases; Go still rejects unrelated canonical names before cleanup.

## Full standalone Rust workflow

Parent `06a8b73a19b6` includes upstream main `7c35e6274737`, reverified before
publication. A is the validated readiness CLI (`d4eb2c81` binary); B adds only
this inventory change (`6a5b0185`). Both use the same previously validated
experimental verified-stream engine `1fb3565bb5ba`, official gzip Rust image,
unchanged benchmark module and normal packaged registry route.

Six fresh independent engine/Cargo states, ordered AB/BA/AB. Ordinary CLI
image-driver provisioning is inside the first-check timer; every warm command
also keeps normal image-driver discovery/start. There is no listener. Three
within-run repeats are summarized before computing three independent pairs.

Milliseconds; positive paired saving favors B. Separate medians do not subtract
to the paired median. All observations, losses and native comparisons remain
in results.json. First check already includes provisioning, not an additive row.

| Flow | A median | B median | Paired saving [min, max] | Favorable | B paired native overhead |
|---|---:|---:|---:|---:|---:|
| Provision + first check, profiled | 21298.381 | 21157.711 | -544.069 [-2214.094, 3107.931] | 1/3 | +14006.627 |
| Exact check | 559.571 | 514.264 | 48.176 [29.901, 52.923] | 3/3 | +393.872 |
| Application edit | 959.090 | 903.857 | 52.795 [35.074, 91.360] | 3/3 | +603.736 |
| Workspace-library edit | 1107.687 | 1060.316 | 49.895 [28.660, 55.201] | 3/3 | +606.666 |
| bstr 1.12 -> 1.13, profiled | 2387.885 | 2198.165 | 94.219 [72.851, 212.110] | 3/3 | +539.711 |
| Unchanged after upgrade | 541.500 | 506.687 | 34.814 [29.294, 41.087] | 3/3 | +386.720 |

Exact/application/library paired native-overhead savings are 36.407/43.064/
35.800ms, also favorable in every pair. The external-upgrade total improvement
is larger than its inventory-phase improvement; do not attribute every observed
millisecond of compiler/network/scheduling variation to the filter.

This is a consistent warm-loop improvement on this host, **not native parity**:
all representative flows still lose to Cargo. There is **no net cold-flow win**;
paired cold overhead worsens 758.617ms. The candidate's cold range is
20.236-21.842s. Three pairs do not establish reliable tails or a universal gain.

## Mechanism and host dependence

wcprof first identified the normal CLI's unfiltered inventory cost. A read-only
20-pair probe returned the same selected names/order while reducing inventory
time from 135.861 to 84.923ms; paired saving 51.134ms [45.048, 74.417], 20/20.
The host contained 58 retained containers and the probe selected 6.

The full-flow controller captures and checks the complete unrelated ID/name
inventory outside timers before/after each run. It stayed unchanged at 58
containers; each run temporarily owns its native/engine containers in addition.
Unrelated names remain local-only; published evidence contains count and digest.
A host with only its selected engine need not see the same saving.

Actual exact-check inventory spans fall from 140.109 to 88.018ms; paired saving
51.836ms, 3/3. Application/library inventory savings are 51.420/52.625ms, 3/3.
Cold inventory improves 55.462ms and connect improves 44.606ms, 3/3, but the
full cold result still loses. The existing approximately 1.08s readiness RPC
remains on both sides. Phase medians are overlapping boundaries, not additive.

All 72 inspected ordinary/profiled command traces contain exactly one successful
inventory command with the expected A/B arguments. See driver-summary.json,
inventory-mechanism.json and phases.json. The mechanism audit is a post-capture
derivative; it does not rewrite raw telemetry or change headline timings.

## Correctness and reproduction

The fake-command repro fails Docker's expected filter in all three repetitions
against unchanged production; other backend command cases pass. After the fix,
the driver package passes three race-enabled repetitions (1.092s initially,
then 1.081s with the owned-container fixture compiled). The publication clone
independently passes in 1.078s. Input hashes match the measured build exactly.
See validation/ and build.sh for pinned Go, flags, dependency/cache paths.

The real-Docker contract passes in 2.899s including race overhead. It creates
four uniquely labeled stopped containers from a preinstalled image; checks
prefixes, dotted exact names, multiple alternatives, missing names, ordering and
stable inventory; then validates ID/name/image/owner/status before cleanup.
It never pulls/removes images or deletes pre-existing containers. The old
`DRIVER_TEST` integration fixtures have shared names/image cleanup and were not
enabled on this shared host. Safe contract reproduction:

```sh
DAGGER_TEST_DOCKER_INVENTORY=1 \
DAGGER_TEST_INVENTORY_IMAGE=YOUR_ALREADY_INSTALLED_IMAGE \
go test -race -count=1 -run '^TestDockerContainerInventoryContract$' ./engine/client/drivers
```

The command uses `/bin/true`, so provide a compatible Linux image. Unit coverage
also checks custom-target reuse/start, cleanup enabled/disabled, preserved
versions, common postfiltering, empty inventory and cancellation propagation.

The full comparison passes 36 complete maintained wcprof captures, 18 cache
analyses, 36 native/retrieved affected-crate comparisons and 54 actual ordinary
timed-command execution audits. It covers the real selected bstr versions,
unaffected memchr reuse, compile failure/repair/failing-source revisit and
restart reuse. Every cold consumes the same full 316873658 compressed Rust
bytes. Warm replay drift is -0.0..-0.1%; cold -2.9..-3.9%. No precise cold
what-if savings are claimed.

The frozen controllers retain measured-owner paths and hash guards. They are
provenance, not a portable zero-install demo. For a new comparison, create new
owners, build both CLIs with identical flags, update explicit identities before
capture, then run run-fullflow.py --execute, analyze-fullflow.py, audit-ordinary.py,
summarize-fullflow.py, phase-summary.py and driver-summary.py sequentially. The
unchanged adapter is recorded in the parent readiness evidence at
`hack/bench-cli-readiness-current/cli-provision/run-cli-provision-check.py`.
Require every gate/count, not just process exit 0.

Docker, CLI, engine/native images and local module were preinstalled. Native
Cargo runs through docker exec, not directly on the host. First checks/upgrades
are profiled; other timed checks omit --profile but export local OTLP. Host/CDN
caches are not purged. Old-engine GC is disabled only to preserve unrelated
user/build engines; Go tests cover its unchanged selection semantics. Pinned
rsync delivery and root-toolchain preparation remain explicit module experiments.

No complete-install, artifact/fmt/Clippy/test-command, build.rs/features/concurrency,
macOS or remote performance claim. No raw telemetry, private analyzer, binaries,
unrelated inventory names or OCI images are published. No PR or maintainer
approval is claimed. The Rust performance goal remains unmet.
