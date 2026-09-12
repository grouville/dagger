# Dang parse-once evaluation

**Experimental proposal, not active production wiring.** Parsing each module
directory once per declaration/runtime invocation saved about **94 ms** in this
matched standalone Rust generator experiment. It does not make Dagger faster
than Cargo: the candidate still adds about **0.98 seconds on application edits
and 1.21 seconds on library edits** against the containerized Cargo reference.
The [Rust developer-loop goal](../bench-rust-loop/stack-index.md) remains unmet.

## Change and fit with Dagger

The native Dang v2 SDK previously parsed the source independently to discover
self-type names, then the Dang library parsed the same directory for declaration
or execution. The [library patch](patches/library.patch) adds an invocation-local
`DirectoryPreparation` callback to new `DeclareDirWithPreparation` and
`RunDirWithPreparation` entrypoints. Existing entrypoint signatures remain.
The [SDK patch](patches/sdk.patch) inspects those freshly parsed blocks before
inference to prepare the same self-type schema entries, eliminating the separate
best-effort parse. Declaration and execution still each parse their own source;
this is not one parse shared across sessions or between these two operations.

No AST, schema, live client, Workspace, resource handle or compiled action is
cached across invocations. The ordinary module/cache ownership and service
cleanup boundaries remain. Authoritative parse/configuration errors still abort;
file-local imports, sibling declarations, unused public types and existing
renamed-module seed behavior (including `RenamedRenamed`) are preserved. The
callback must inspect, not retain or mutate, blocks that inference later mutates.
Native imported modules do not inherit a context hook. API naming/shape still
needs upstream Dang review and release; the SDK should then use a normal version
bump. The [local replacement](patches/prototype-dependency.patch) is **only** a
way to reproduce the unpublished library, not proposed production vendoring.

## Matched standalone results

All numbers below are process milliseconds, including final artifact export.
Each row uses novel edits and independent persistent Cargo caches. Same CLI,
two separately prepared engines, ordinary new `dagger generate -y` processes;
no listener or persistent user-side session. Native is `cargo build` through
`docker exec`, not host-native Cargo. Full debug settings and the same toolchain
and Cargo flags are used, without custom linker/profile/feature speedups.

| Batch / edit | Native median | Control median | Candidate median | Median paired saving | Candidate faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pilot n=3 / application | 140.202 | 1234.840 | 1168.143 | 54.579 | 3/3 |
| Pilot n=3 / library | 183.310 | 1517.983 | 1401.062 | 116.921 | 3/3 |
| n=30 / application | 141.043 | 1216.749 | 1118.654 | 93.702 | 29/30 |
| n=30 / library | 186.145 | 1475.657 | 1394.936 | 93.491 | 23/30 |

The n=30 application p95/max changes from 1314.811/1334.948 to
1199.152/1215.836 ms; library p95/max from 1623.570/1833.171 to
1591.839/1711.503 ms. P95 is nearest rank. The worst paired regressions remain:
73.024 ms application and 217.768 ms library. Paired native overhead medians are
1067.213 → 976.151 ms application and 1282.101 → 1208.128 ms library.
The candidate's paired median slowdown versus native remains 7.836× and
7.496×, respectively.
Do not subtract independent medians to obtain a paired median, sum these gains
with earlier experiments, or treat n=3 as a robust estimate.

The harness rotates all six control/candidate/native orders; n=30 includes five
of each order per scenario. Setup and sample-zero warmups are retained but
excluded from these statistics. The engines have different prior histories and
readiness is explicitly `asymmetric-or-unknown`. Order rotation does not make
OS page caches, network or engine histories identical. This is warm invalidation,
not first installation, cold image delivery, exact-hit performance, external
dependency upgrades, all Rust projects, macOS/remote operation or a Bazel result.
The two-package fixture is **not the official Rust module**.

### Attribution and correctness

Maintained wcprof accepted n=30 traces show `ModuleSource.asModule` call-exec
self medians of 120.7 → 71.9 ms (application) and 119.7 → 72.2 ms (library).
`rust:Rust.build` self medians are 133.95 → 87.3 and 134.0 → 87.4 ms.
These are analyzer attribution metrics, not isolated parser CPU or additive
whole-process savings. Candidate library class statistics use 28 accepted
measured traces; other n=30 class cohorts use 30. Cargo exec medians stay similar:
219.068 → 220.602 ms application; 277.881 → 279.529 ms library.

- Timed application builds rebuild `prototype-app`; library edits rebuild
  `prototype-library` and `prototype-app`. Accepted post-timer `build-messages`
  traces execute no replacement Cargo action. Observed package/action sets match
  on the two rejected traces too, but incompleteness prevents proving no other
  hidden work there. Cached Cargo logs alone are not execution proof.
- The fixture publishes two executables, an rlib and a roughly 30 MB staticlib.
  Executable bytes/behavior, target/freshness sets, source identity, sentinel,
  ancestor modes and generated-subtree boundaries pass. There are no mode
  discrepancies on either engine in these batches.
- **Not every artifact is raw-byte identical.** All 32 pilot and 248 n=30
  cross-side archive comparisons used the existing strict compiler-member-name
  equivalence guard: ordinary member payloads, ordering, index/padding and raw
  archive layout are checked after only verified identifier/link-reference
  substitutions. Raw hashes remain recorded; artifacts are never normalized on
  disk. This fixture-specific exception is not a general semantic archive test.

See [harness correctness rules](../bench-rust-generators/README.md) and the
retained [n3](evidence/n3-harness-summary.json) /
[n30](evidence/n30-harness-summary.json) local summaries. Their original
`actual_execution_verified=false` / pending-audit statuses remain unchanged;
the separate profile evidence below records the later, partially complete audit.

### Rejected captures and smoke failures remain failures

The n30 corpus has **246/248 passing wcprof gates**: 122/124 timed traces and
124/124 diagnostic traces, including warmups. Candidate library samples 7 and
11 lack `wcprof.session_complete`; both are rejected, not repaired or excluded
from process timing statistics. The pilot has **31/32** passing gates; candidate
library sample 2 has the same missing-carrier rejection. The compact summaries
retain exact trace IDs and full failure messages. A missing carrier does not
prove the parser caused loss, and absence of observed extra work is not complete
coverage. No native-recorder coverage is claimed.

Accepted n=30 captures account for 74,057 declared and received engine spans.
Their reported replay drift ranges from -0.2% to -0.0%; small replay drift does
not make either missing-carrier capture acceptable.

The separate 16-call Dang smoke run stays **functional-failed**: four successful
`speak`/`repaired` calls (both engines) failed the assertion that prints appear
on stderr at default verbosity. Returned values, expected failures, own-type
calls, sibling edits/repeat and source repair checks passed. Raw telemetry
contains the expected successful prints, owned by finalized `Probe.speak`
spans with complete CLI ancestry. Failure prints have `Probe.failure` owners.
Source supports normal completed-log suppression: `api call` starts at verbosity
1, completed-row expansion requires 5, and collapsed rows hide inline logs;
`-vvvv` reaches 5. That rendering explanation is not a replacement successful
test or a rewrite of the four original assertions.

Smoke gates are **14/16**: candidate `sibling` and `runtime-failure` lack carriers.
All expected print-owner checks pass locally, but the latter failure trace is
not a complete capture. Parse-invalid fails before executing `Probe.speak`;
repair emits its own distinct marker. [Smoke audit](evidence/smoke-audit.json)
retains the failures, exact owners, timestamps, markers and gate text. These
functional probes are not matched latency measurements.

## Reproduce the proposal

Prerequisites: Linux/amd64 Docker, Git, Python >=3.11, GNU `ar`, Go 1.26.8, a
compatible Dagger bootstrap CLI, the pinned library ZIP and Go dependencies,
and access to the dev-build dependencies/registries. Follow the repository's
engine-debugging and telemetry-capture skills. Network/bootstrap availability
and the maintained external wcprof analyzer are not supplied by this bundle;
this is not a fully self-contained or cross-platform reproduction.

1. Create two new owned source worktrees at
   `bfb0c200efd6395656bc831da0b810d5027f289b` (upstream
   `9b235855b35bf4508b1a5ddf64a5f36b6033a188`). Leave the control unchanged.
   Verify SDK/go.mod/go.sum hashes against
   [prepared-source.json](evidence/prepared-source.json).
2. Obtain the Go module ZIP for `github.com/vito/dang/v2@v2.1.3` (e.g. the
   standard Go proxy's `github.com/vito/dang/v2/@v/v2.1.3.zip`). Require SHA256
   `05783580315b232258153f9a8915008382e8967294467a1ea4512449c8d4348b`.
   The tag's source commit is `2d592c8d71007a5242c0f18c6220fedd3423eee5`.
   Extract this ZIP into the candidate's new `internal/dang-parse-once/`;
   its archive prefix creates `github.com/vito/dang/v2@v2.1.3/` underneath.
   Include the entire library, including C and embedded files, in the build
   context. Do not modify the module cache.
3. In that extracted module, check/apply `patches/library.patch`; in the
   candidate engine root check/apply `patches/sdk.patch` and
   `patches/prototype-dependency.patch`. They are ordinary `git apply` patches,
   relative to their respective roots. Verify the resulting source hashes in
   the preparation manifest. A future upstream release replaces this local
   replacement; do not silently substitute a different Dang release.
4. With Go 1.26.8, `GOTOOLCHAIN=local GOWORK=off GOFLAGS=-mod=readonly`, and an
   owned writable `GOCACHE`, run these serially. `GOPROXY=off GOSUMDB=off` works
   only after dependencies are populated:

   ```sh
   # In the extracted library:
   go test -v ./pkg/dang -run '^TestDirectoryPreparation' -count=1 -timeout=2m
   # In the candidate engine worktree:
   go test -v ./core/sdk/dang/v2 \
     -run '^(TestModuleDeclaredTypeNamesFromParsedFiles|TestPreparedSelfTypes.*)$' \
     -count=1 -timeout=2m
   ```

   Recorded package results are 0.112s and 0.119s, both PASS (not benchmark
   results). They cover same parsed-block use after source mutation, error/
   cancellation identity, empty/config-error cases, file-local imports,
   visibility/namespacing and preparation before declaration/runtime. No race
   detector, full Dang suite or live-service cleanup test was run.
5. Build/deploy each source with the supported pinned workflow, using different
   unique names, image aliases, volumes and output directories. The recorded
   candidate command is equivalent to:

   ```sh
   dagger --x-release 00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21 \
     api call dev --docker=unix:///var/run/docker.sock deploy \
     --name=UNIQUE_ENGINE --image=localhost/UNIQUE_ENGINE \
     --platform=linux/amd64 --debug-endpoint=false --output /owned/bin-output
   ```

   Independently inspect container IDs, actual image IDs and image aliases
   before/after each run; a name alone is insufficient. Do not prune shared
   state. Use the **same control CLI** against both engines, not the candidate's
   separately built CLI. [Recorded integration command](evidence/integration-tests.json)
   returned exit 0 and the [log](evidence/integration-tests.log) reports 36 passed,
   including the intended invalid/skipped-module diagnostics. It selects Dang
   self calls, directives/defaults, workspace/private args, versioned syntax,
   managed-module and generator validation; Go self-calls are explicitly skipped.
6. Start a fresh local OTel receiver. Set generic, logs and metrics endpoints and
   `OTEL_EXPORTER_OTLP_TRACES_LIVE=1`; record opt-outs/environment as in
   [metadata](evidence/n30-metadata.json). Keep builds/tests/analyzers out of the
   timing window. Reuse the tracked harness and unchanged tracked module:

   ```sh
   python3 hack/bench-rust-generators/compare-generators.py --execute \
     --dagger /absolute/path/to/control/dagger \
     --module /absolute/path/to/repo/hack/bench-rust-generators \
     --fixture /absolute/path/to/repo/hack/bench-rust-generators/fixtures/workspace \
     --before-engine 'docker-image://localhost/CONTROL?container=CONTROL&volume=CONTROL&cleanup=false' \
     --after-engine 'docker-image://localhost/CANDIDATE?container=CANDIDATE&volume=CANDIDATE&cleanup=false' \
     --before-image-id sha256:ACTUAL_CONTROL_IMAGE \
     --after-image-id sha256:ACTUAL_CANDIDATE_IMAGE --samples 3
   ```

   Pilot first, then a new invocation with `--samples 30`. Every invocation owns
   new workspaces/frozen Git-root module/cache keys; final outputs persist within
   each run. The harness removes only its exact owner-labelled native container;
   evidence remains. No cache reset or existing-engine removal is required.
   After timing, extract complete traces by process/root identity, then entire
   trace ID; run maintained wcprof completion/drop/replay gates and verify the
   actual Cargo execution sets. Use the existing
   [profile-command.py](../bench-rust-loop/profile-command.py) / capture workflow,
   not truncated time slices, replayed logs or synthetic completion markers.

## Pins and retained evidence

The tested engine base is bfb0 above, not a claim about current `main` or later
rebased commit IDs. Original preparation was at `26040b59aa`; relevant source
hashes matched on bfb0. [Prepared-source](evidence/prepared-source.json) retains
its historical `SOURCE_ONLY_NOT_YET_COMPILED` status; [unit results](evidence/unit-results.json),
integration records and runtime evidence are subsequent stages, not edits to it.

- Go 1.26.8 binary SHA256:
  `d9a2fa19c7ef8b57f420012c21f49f235c46f08a68c12077d9c753dbb6ccdc34`.
- Same CLI SHA256:
  `ff5acf117d2fdab17dbbd0581178843c01f0a6c962736322814b5d0b7a00c576`.
- Control image: `sha256:8683dc8fbb0f3585afe8e2adeb09738971a462b17f922ef4ac86d75fe64c9004`.
  Candidate: `sha256:5fecb56d6d22b672c00c03b3c14cca737477406f70339087d678bb2c48b6ab49`.
  [Run record](evidence/n30-run.json) retains unchanged container IDs and alias
  checks, launch arguments and source/fixture hashes.
- Harness SHA256 `b3d96491306750aa0e9a81c549ea4427846c0ff6ea0be964a05597d84903aa38`;
  module `main.dang` `48c95bb11c503e94cda52d61f1313f458f3813714d83acd703ed8996660f4164`;
  module config `80ceb12a068bb2c86041ba35bdcb24edada8ae228b77450de2ce917caa2ec8e5`.
  These match the existing tracked generator module, so no framework copy is needed.
- Rust image `rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b`;
  flags `--workspace --locked --message-format=json-render-diagnostics`.
- Maintained analyzer SHA256
  `de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba`.
  Its private implementation and the large raw telemetry corpus are not included.

[n3 timings](evidence/n3-timings.csv), [n30 timings](evidence/n30-timings.csv),
[n3 profiles](evidence/n3-profiles.csv), [n30 profiles](evidence/n30-profiles.csv)
retain all rows, including warmups/rejections. CSV copies normalize CRLF to LF
only; patch bytes remain exact. Compact [n3](evidence/n3-profile-summary.json) /
[n30](evidence/n30-profile-summary.json) summaries retain counts, selected class
statistics, failures and corpus/extractor hashes without embedding full spans.
The CSV `kind=pilot` label is an extractor label also used for n30, not its sample
count; use the batch filenames and `samples_per_scenario`.

Original local evidence (historical references, not portable dependencies):
`/tmp/dagger-dang-parse-once-kb5Mrq`,
`/tmp/dagger-dang-parse-once-bfb0-test.AzU3qOnB`,
`/tmp/dagger-rust-generator-pair-2ktyg4uo` (n3),
`/tmp/dagger-rust-generator-pair-iw520xrb` (n30), and
`/tmp/dagger-dang-parse-once-smoke-analysis-jp60o2_o`.
Full original artifact manifests, logs and raw traces remain there but are not
reconstructed by these compact reports. Fresh wcprof certification requires a
new capture and access to the maintained analyzer; public timing/source evidence
alone cannot reproduce its complete structural audit.
