# Collections discovery: reuse the core schema for artifact trees

September 25, 2026. On Kyle's greetings-api, a further engine change takes
`dagger check -l --all` from **2.572 s to 2.301 s median**, including CLI exit.
Eight alternating pairs favor the candidate; all 16 listings match the same
14 expected checks byte for byte. This is **271 ms / 10.5% less elapsed time**
on top of the previous experimental stack. The 500 ms target remains unmet.

## What changed

Artifact discovery creates a standalone DagQL server for each module tree.
Artifact evaluation also creates these servers under the current caller.
Previously, `dagqlServerForModule` installed every core resolver afresh each
time: reflecting arguments, formatting descriptions and reconstructing schema
metadata. The engine already has a prepared core schema and an independent
schema-fork mechanism, used by its other schema builders.

The artifact path now uses that existing mechanism through
`buildSchemaWithView`. It forks the prepared **core** schema and installs the
selected user module into the new server. It preserves the previous empty
API view for discovery, independently of the module's authored version.
Runtime calls still use their module's normal dependencies and version.

This is ordinary engine code, enabled by a normal source build. It introduces
no additional result cache, file watcher, TTL, global module-name cache, or
cross-session user-module server reuse. User-module installation and caller
defaults remain fresh; forked schema tables and roots remain independent.
The existing fallback works without a forkable core, including persisted
module decoding tests. It does not require distributed caching.

This removes repeated full core-schema construction from artifact traversal
and evaluation. It is not an O(1) discovery algorithm: each independent fork
still copies schema tables, installs user fields, and walks the selected
artifact graph. The gain is from reusing prepared immutable definitions and
avoiding reflection, parsing and allocations on every installation.

## Measured comparison

The app is `kpenfound/greetings-api@14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`,
with `dagger/go@1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. Both sides retain
the configured backend Go base, Playwright service, SDK generators and module
cache policies. Each invocation starts a new CLI process and session.

The control is the preceding engine stack. Both sides include the experimental
Dang syntax cache, split TypeScript imports, prebuilt TypeScript runtime, and
the [Node/tsx startup caches](collections-node-startup-performance.md).
Only the engine's artifact-server construction differs; CLI, app and SDK
payloads are identical. **The absolute 2.301 s result is not a normal branch
build or Kyle's unmodified branch.** The engine improvement itself does not
depend on those prototypes.

| Warm listing | Control | Candidate |
| --- | ---: | ---: |
| Median, 8 invocations each | 2.572 s | 2.301 s |
| Range | 2.447–2.731 s | 2.213–2.452 s |

Telemetry remains enabled, including the CLI's Cloud exporter. No Cloud engine
or distributed result cache is used. The broken SSH-agent environment variable
is omitted symmetrically. Builds, tests and profiles are outside the measured
warm series. Measured-series host pressure averages 9.33% CPU some-pressure
and 0.21% full I/O pressure. Output is validated, not merely exit status.

Each edit below is applied before immediately running the command. These are
single observations per version, not distributions. Expected keys are checked
independently and complete output is compared between versions; source is
restored at the end.

| Edit | Control | Candidate |
| --- | ---: | ---: |
| Comment only | 2.945 s | 2.345 s |
| Rename test | 2.501 s | 2.347 s |
| Add test | 2.523 s | 2.432 s |
| Add Go module | 2.731 s | 2.552 s |
| Restore source | 2.481 s | 2.214 s |

## Profile evidence

Separate 15-second CPU profiles cover four commands each. CPU attributed to
`dagqlServerForModule` drops from **1.85 s to 0.34 s cumulative**, about 82%.
The candidate's remaining cost primarily installs user-module fields. These
are CPU samples across four commands, not elapsed savings for one command.

Separate wcprof captures have zero dropped events and zero open operations.
They show collection expansion (`Artifacts.__itemsJSON`) at 868 → 709 ms and
the final metadata-only `Workspace.artifacts` at 64 → 20 ms. Initial module
loading varies in the other direction, 1.146 → 1.220 s, including slower Node
processes in that candidate capture. The full profiled commands are
2.616 → 2.498 s. These snapshots explain boundaries; the alternating,
unprofiled series above establishes the reported gain.

## Cold starts

Each cold invocation uses a new Dagger data volume and a ready engine with
the same packaged SDK images. Engine provisioning, image distribution and
host-cache eviction are outside this definition. The four invocations run
serially in control/candidate/candidate/control order; each engine is stopped
before starting the next.

| Order | Control | Candidate | Full host I/O pressure, control / candidate |
| --- | ---: | ---: | ---: |
| Control first | 26.965 s | 26.198 s | 0.8% / 1.0% |
| Candidate first | 47.900 s | 41.404 s | 46.0% / 36.2% |

All four outputs are correct. The long pair coincides with much greater disk
pressure, consistent with the [earlier cold variance investigation](collections-cold-cache-analysis.md).
This is host-wide evidence, not attribution to a particular process. With only
two cold samples per version and that variation, no stable cold speedup is
claimed. The initial candidate population, outside these pairs, was 26.901 s.

## Correctness and upstream scope

Focused core tests pass: the actual artifact-server path forks core state,
preserves its unversioned view, reconstructs caller-specific fields, and keeps
mutations out of other callers and the template. Existing prepared-schema
concurrency/scope and persisted-module-enum tests also pass.

Ten focused artifact/collection integration cases pass, including nested
subtests: use after the discovering session closes, workspace edits, module
boundaries, core selection, explicit entrypoints, check caching policy,
dimension selection, schema-only listing, enum keys and batch replacement.
No selected tests are skipped. This is targeted validation, not a claim that
the full integration suite ran.

The production change is limited to `core/modtree.go` and
`core/schema_build.go`, with a regression test in `core/schema_build_test.go`.
It is committed separately as
[`cdf6eaad1c`](https://github.com/grouville/dagger/commit/cdf6eaad1c), so it can
be reviewed or cherry-picked without the benchmark archive.
It is a candidate for upstream independently of the experimental SDK patches.
It preserves the existing schema-fork ownership and mutation rules rather than
introducing a new caching policy.

## The next boundary toward 500 ms

A separate diagnostic sends only `{ __typename }` using
`dagger -m core api query`, from the same app checkout and against the candidate
engine. Its five unprofiled invocations take **723–821 ms, median 746 ms**.
This does not discover artifacts and is not a substitute benchmark or a formal
lower bound for another command; it exposes substantial fixed CLI/session cost.

A separate CLI execution trace for that diagnostic records **312 ms blocked
in tracer-provider shutdown**, while Dagger client close accounts for about
5 ms. CPU usage is only 50 ms in that profile. This supports targeting the
export boundary as well as module discovery. It does not establish a fixed
sleep, justify dropping telemetry, or imply that other exporter shutdowns can
be parallelized to reclaim those 312 ms.

The real listing still starts TypeScript processes to load declarations and
then expands collections. Removing those runtime starts, reducing repeated
Dang preparation, and retaining telemetry delivery while reducing synchronous
export latency remain necessary directions. The static SDK work discussed
earlier addresses one of these boundaries; this patch does not duplicate it.

Raw timings, output, host pressure, scripts, test summaries and profile hashes
are in [the evidence directory](collections-qa-performance-data/artifact-schema-fork/).
See [the start guide](collections-performance-start.md) for the branch,
normal build and experimental-stack distinction.
