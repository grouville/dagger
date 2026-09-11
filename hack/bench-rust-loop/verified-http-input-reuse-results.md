# Verified HTTP input reuse, 2026-09-10

## Finding and scope

A matching checksum can reuse HTTPState's retained, verified canonical snapshot
without contacting the origin. Unit/race tests and an actual engine-restart
integration test pass. The pinned Rust source-sync tool no longer performs its
two warm HTTP revalidations. No new cache, daemon, service, API argument, or
session-reuse mechanism is introduced.

**The local Rust timing benefit is small and variable.** Preserve this as a
separately reviewable cache-semantics/performance candidate, not a major Rust
speedup. It does not improve an empty HTTP cache or fix cold Rust image delivery.
The pinned-source-sync module setting remains opt-in; this result does not
justify promoting it to a universal production default.

## Contract and Dagger cache model

This is an intentional semantic change: with a nonempty matching checksum,
retained bytes pin the cached representation. Changed origin content, outages,
new ETag/Last-Modified headers, and signed-URL expiry are not observed on that
hit. Maintainers must review this contract, not just its speed.

The fast path runs under the existing HTTPState mutex and requires an actual
owned snapshot, reopening its persisted snapshot link when necessary. A digest
alone is insufficient; a broken snapshot link still fails closed. The existing
fileResult path derives independent filename/permission-specific immutable
files. Existing snapshot-owner lease synchronization, last-modified identity,
retention, accounting, and release hooks remain unchanged.

An absent/empty/different checksum still follows ordinary fetch/revalidation
and checksum verification. Explicit authHeader and experimentalServiceHost
arguments still bypass HTTPState. URL-embedded credentials and signed query
parameters are URL identity, not those explicit arguments, and can use this
fast path. The change does not create a multi-version, checksum-keyed store:
after an unpinned request replaces the canonical representation, an old pin
must fetch/verify again or fail.

## Provenance and controls

Upstream main was checked at f4e83a5250ca4aa392bacb3cd4b51bd9b50b2262.
Both engines were built through the repository's pinned dev workflow at
00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21, with Go 1.26.8 and go-runewidth 0.0.30:

| Variant | Source | Engine image ID | Engine binary SHA256 |
| --- | --- | --- | --- |
| Before | clean 5a8be38e04ff43de937c56b4754ae4141dee36a2 worktree | 5270c81fccdddf16036c3678d4055199cf8bab53eadbc9777053be0b92bab8cf | c2d7fddf01e4ea0fb7d181591201ce789361c2e1adc5328c959cecf094543006 |
| After | same parent plus this HTTP change | a88be98f9fd15cd2bb8ab5c59f2979c8b36f2409cf4340dba0121f914be66823 | 54315c5b094010dd9b2c9e8c5596b2c945623271a164c48cb5c4244e269951c9 |

The clean detached worktree's binary has no embedded Go VCS stanza; its checkout
was explicitly verified. The candidate records 5a8be38e + dirty. Final test
counter strengthening and public-doc wording clarification happened after the
engine build; the measured core/http.go runtime implementation is unchanged.

Every measured invocation uses the same CLI, /tmp/dagger-rust-cli-width-after,
SHA256 280da457914068c215f9bb8aada21a998f93b7ffd4ac4f17759c6943f5d06748
(Go 1.26.6). Module, Rust image, flags and native lifecycle are the same as
[the source-sync delivery experiment](source-sync-delivery-results.md).
No Cargo flags, source reconciliation, cache namespace rules, or outputs change.
DO_NOT_TRACK=1, isolated XDG state and localhost-only OTel apply. No builds or
tests ran concurrently with timings. Native means Cargo through docker exec,
not a directly installed host Cargo.

## Standalone exact-check comparison

Thirty alternating pairs per run, with one excluded but retained warmup pair;
same prepared ripgrep workspace and pinned-tool setting, separate engines.
Native wcprof is off for these timings; local OTel remains enabled. All outliers
and warmups are in [the raw paired CSV](verified-http-input-warm-pairs.csv).

| Run | Before median [min, max], ms | After median [min, max], ms | Median paired saving, ms |
| --- | ---: | ---: | ---: |
| Initial, unequal prior engine history | 400.55 [383.49, 471.35] | 405.14 [380.40, 541.44] | -2.69 |
| Repeat, both initially empty engine volumes | 413.80 [382.45, 461.70] | 404.80 [390.21, 534.89] | 7.94 |

The initial candidate engine had also run integration tests, so that run is
not the controlled headline comparison. The repeat gave each engine a fresh
volume and the same Rust warmup. It improved the difference of medians by
9.00ms, but that is not a guaranteed gain on every invocation. These are exact
hits, not first-install or invalidation speedup evidence.

In the repeat's last pair, the process actually regressed 405.90 -> 419.86ms.
Both OTel wcprof gates pass: 152/150 operations, 137/135 declared and received
spans, one root, no open/lost spans or links, and -0.1% rounded replay drift.
The before capture has package-fetch envelopes of 7.78 and 17.70ms; after has
neither. They overlap other work and cannot be subtracted from total time.
Process accounting is 28.11 + 366.00 + 11.80ms before, versus
29.35 + 377.84 + 12.67ms after (before root + root + after root).

## Real edits and external dependency changes

Each engine also ran seven novel application edits, seven workspace-library
edits, exact checks, failure -> repair -> old failure -> repair, and one external
bstr 1.12.0 -> 1.13.0 upgrade in independent Cargo cache namespaces. The engine
images/tool inputs were already available; initial Cargo population is retained
in each run's first-use.json, not presented as full cold onboarding.

The two complete runs were sequential batches, not interleaved engine A/B
invalidation trials. **Do not attribute their differences to this patch.**
Within each batch native/Dagger order alternates for the seven-sample scenarios;
the upgrade is native-first before and Dagger-first after.

| Scenario | Before native / Dagger, ms | After native / Dagger, ms |
| --- | ---: | ---: |
| Exact, median of 7 | 106.16 / 441.66 | 101.34 / 416.92 |
| Application edit, median of 7 | 288.94 / 832.74 | 276.66 / 795.69 |
| Workspace-library edit, median of 7 | 457.02 / 1000.13 | 471.75 / 1066.38 |
| External library upgrade, one transition | 1790.78 / 2242.76 | 2265.79 / 2678.46 |
| Upgrade follow-up, one sample | 100.50 / 435.07 | 161.48 / 928.12 |

Both sides rebuilt the same ten packages for the external upgrade, selected
bstr 1.13.0, retained unrelated memchr, and preserved the locked manifests.
Both engines correctly rejected the revisited failing source. Raw samples,
including regressions, are in [the invalidation CSV](verified-http-input-invalidation.csv).
The candidate's observed edit overhead remains roughly 519ms for application
edits, 595ms for workspace-library edits, and 413ms for that external upgrade.
Exact warm checks still do not beat the native control.

The 928.12ms follow-up is retained, not discarded. Its complete wcprof trace
contains no new container execution or HTTP fetch. Time is 85.90ms before the
root, 828.55ms inside it, and 13.67ms after. Delays are broad: Docker's probe
36ms, first Info envelope about 81ms, module loading 65ms, and checks/Rust.check
self envelopes 131/152ms. This is not evidence of extra crate recompilation;
the underlying cause of that broad slowdown is not established by this capture.

Eight selected OTel invalidation/upgrade/follow-up captures all pass the
maintained analyzer's completeness/structural gates, with rounded replay drift
between -0.1% and -0.0%. Six native diagnostic captures have 548-591 operations,
ten roots, no open/dropped events and -0.0% rounded drift. Native captures cover
only part of the process and do not establish complete cross-session causal
attribution; the single-root OTel analysis and process boundaries supply the
whole-flow view. Native/OTel what-if savings are hypotheses, not measured gains.

## Correctness and reproduction

```sh
GOCACHE=/tmp/dagger-rust-go-cache go test ./core -run '^TestHTTPState' -count=1
GOCACHE=/tmp/dagger-rust-go-cache go test -race ./core -run '^TestHTTPState' -count=1
python3 -m unittest discover -s hack/bench-rust-loop -p test_compare_cli.py -v
```

Unit tests exercise offline/changed-origin reuse, unpinned ETag/Last-Modified
requests, empty and changed/invalid pins, independent names/modes/timestamps,
snapshot reopen/missing links, eight concurrent resolves, and cancellation.
The new reuse test fails against the pre-change core/http.go supplied through a
Go overlay (checksum mismatch after the origin changes). Race tests pass in
1.168s (final approved rerun: 1.175s); the five harness tests pass. Unit snapshot
fakes do not prove real GC.

For real integration, first build/export the engine through the pinned dev
workflow. Set _EXPERIMENTAL_DAGGER_CLI_BIN to that CLI and
_DAGGER_TESTS_ENGINE_TAR to its exported dev engine tar, then:

```sh
# In each respective worktree, choose its unique before/after name and image.
# The current dev loader expects the name to exist; this run created a stopped
# disposable placeholder only after verifying the name and volume were unused.
# The normal dagger-engine.dev is never replaced or reset.
DO_NOT_TRACK=1 dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 \
  api call dev --docker=unix:///var/run/docker.sock deploy \
  --name=dagger-engine.rust-http-after-5a8be38e \
  --image=localhost/dagger-engine.rust-http-after-5a8be38e \
  --platform=linux/amd64 --debug-endpoint=false --output ./bin
DO_NOT_TRACK=1 dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 \
  api call dev --docker=unix:///var/run/docker.sock engine-tarball \
  --output /tmp/dagger-rust-http-after-engine.tar
```

```sh
env -u DAGGER_ENGINE DO_NOT_TRACK=1 \
  _EXPERIMENTAL_DAGGER_RUNNER_HOST=container://dagger-engine.rust-http-after-5a8be38e \
  GOCACHE=/tmp/dagger-rust-go-cache \
  go test ./core/integration \
    -run '^TestHTTP/(TestHTTPChecksum.*|TestHTTPETag|TestHTTPAuth|TestHTTPPermissions|TestHTTPCachePerSessions)$' \
    -parallel=1 -count=1 -timeout=10m -v
```

All eight pass; final run 25.681s. The new test counts every origin query read,
changes the origin, gracefully restarts an engine on the same cache volume,
then verifies persisted pin reuse and subsequent unpinned/changed-pin behavior.
The initial host launch used DAGGER_ENGINE, which overrode SDK WithRunnerHost
for nested clients and caused DNS failures in both the existing ETag test and
new test. That failed run is retained; the SDK-compatible launch fixes the
test setup without weakening assertions. Forced GC/eviction, broad platform
and credential-lifecycle coverage remain upstream review/test requirements.
The final unit-race rerun also needs localhost listener permission: its first
restricted-sandbox launch failed in httptest setup before running assertions.

With the same local OTel/XDG settings as the source-sync report, reproduce pairs:

```sh
python3 hack/bench-rust-loop/compare-cli.py \
  --before /tmp/dagger-rust-cli-width-after --after /tmp/dagger-rust-cli-width-after \
  --before-engine container://dagger-engine.rust-http-pair-before-5a8be38e \
  --after-engine container://dagger-engine.rust-http-pair-after-5a8be38e \
  --workdir /tmp/dagger-rust-loop-4dqodx2f/dagger --samples 30 -- check rust:check
```

For invalidation, run the existing run.py command from the source-sync report
with --samples 7 --pinned-source-sync --dependency-upgrade, omit --fresh-engine,
set DAGGER_ENGINE to each prepared engine, and pass its --debug-url. Alternate
--dependency-first between native and dagger. No listen/resident worker is used.

Local evidence (not publicly hosted captures):

- /tmp/dagger-rust-cli-pair-{8k1v0azk,x8p7dk9k}: all paired processes, logs, metadata.
- /tmp/dagger-rust-loop-{blyfx2dz,ca54kpx0}: all Cargo logs, checks, raw native profiles.
- /tmp/dagger-rust-http-input-otel.jsonl and /tmp/dagger-rust-http-*-{trace.jsonl,boundaries.json,analysis.txt,gate.txt}.
- /tmp/dagger-rust-http-{before,after}-build.log and /tmp/dagger-rust-http-after-tar.log.
- /tmp/dagger-rust-http-state-*-tests.log and /tmp/dagger-rust-http-integration*-tests.log.

This is not a validated official-module release, full first-install benchmark,
artifact export benchmark, macOS result, or remote-engine result. The next big
module opportunity remains toolchain delivery; the next connection investigation
should separate repeated Docker transport startup from actual engine handlers.
