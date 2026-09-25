# Try the collections discovery changes

**2026-09-25:** the branch has been rebased onto `main` at `d8f1f0d6d2`.
This includes the merged engine-side Cloud telemetry split (#14303) and
Cloud reachability probe (#14341). The timings below predate that rebase;
they are not measurements of the new base. See the
[rebase validation](collections-main-rebase.md) before comparing shutdown costs.
Commit IDs in earlier reports identify the original measured builds and remain
unchanged in those reports, even though the branch history was replayed.

The engine/CLI branch is
[`grouville/dagger:perf/collections-discovery`](https://github.com/grouville/dagger/tree/perf/collections-discovery),
based on collections PR #14221 at `175dca038268639231c21323cd7aaa1d746617dd`.
The original engine/CLI performance stack ends at `6e6bdfb16a`. Commit
`1c4e948204` also migrates the bundled TypeScript runtime to committed Go
bindings, removing its first-use regeneration. Other later commits contain
tooling, reports and experimental patches. This is a source branch, not a
published CLI release or engine image.

## What a normal build includes

* One CLI listing session, bulk metadata loading, and complete buffered output.
* Indexed artifact dimensions and collection receiver reuse within a request.
* Less repeated module installation and metadata work; prepared schemas reused
  within the same caller/session authority.
* The existing module-config, schema-digest, and shutdown improvements from
  PRs #14179, #14180, #14182, and #14183.
* The TypeScript SDK manifest migration described in the
  [cold-start investigation](collections-cold-performance.md). Rebuild the SDK
  payload; changing only the engine executable will not apply it.
* Finer image-import profiling. The [Go SDK import investigation](collections-go-import-performance.md)
  explains why trimming compiler test files was not adopted: it loses layer reuse
  with the application's Go image.
* Reuse of the public Git probe's refs within the existing session metadata
  cache. The [warm Git investigation](collections-warm-git-performance.md)
  demonstrates the duplicate request removal, with full-command timings still
  too affected by host contention to establish a stable speedup.
* One Dang introspection decode per schema File per session, with independent
  copies for evaluations. The [schema decode investigation](collections-schema-decode-performance.md)
  measures 2.987 → 2.827 s on the experimental stack and validates edits and
  runtime calls; this is an incremental gain over the preceding stack.
* Artifact trees fork the prepared core schema instead of reinstalling core
  resolvers for every module. The [artifact schema investigation](collections-artifact-schema-performance.md)
  measures a further 2.572 → 2.301 s on the experimental stack, with eight
  alternating pairs, real edits and focused integration coverage.
* Start the first analytics upload during command execution. The
  [CLI shutdown investigation](collections-cli-shutdown-performance.md) measures
  754 → 512 ms for a minimal core query; the full listing stays around 2.29 s.
  It also examines Cloud ingestion and records transport experiments that did
  not improve the listing.

The [cold variance and distributed-cache analysis](collections-cold-cache-analysis.md)
separates host disk pressure from code changes and explains which cold work a
compatible remote result could avoid. The measured runs do not use Cloud caching.

The [Node startup-cache investigation](collections-node-startup-performance.md)
adds a separate loader/compiler-cache prototype: 2.905 → 2.586 s in a direct
five-pair comparison on greetings-api, with edit/runtime validation. Its patch
is archived for review and is not enabled by a normal build. The 500 ms goal
remains unmet; the report identifies the remaining sequential boundaries.

The experimental Dang syntax cache and TypeScript SDK bundle changes are
**not enabled by a normal build**. Their patches and validation are in the
[syntax-cache report](collections-syntax-cache-performance.md) and
[latest investigation](collections-next-performance.md). Approximately three
seconds was measured with both experiments; do not attribute that result to
the engine/CLI source alone. Timings are specific to the measured host.

## Build and run

Use the repository's usual Dagger/Docker development prerequisites. The
following uses dedicated engine names and leaves an existing development
engine alone. Building is outside the timed command.

```sh
git clone --single-branch --branch perf/collections-discovery \
  https://github.com/grouville/dagger.git dagger-collections-perf
cd dagger-collections-perf

_EXPERIMENTAL_DAGGER_DEV_CONTAINER=dagger-engine.collections-perf-build \
_EXPERIMENTAL_DAGGER_DEV_IMAGE=localhost/dagger-engine.collections-perf \
  ./hack/build
```

`hack/build` starts a development engine with `--extra-debug`. To measure the
normal engine mode, start the built image with a separate state volume:

```sh
docker run -d --privileged --security-opt label=disable \
  --name dagger-engine.collections-perf-normal \
  -v dagger-engine.collections-perf-normal:/var/lib/dagger \
  localhost/dagger-engine.collections-perf --debugaddr=0.0.0.0:6060
```

From the greetings-api directory, use the **newly built CLI** and select that
engine explicitly (replace the example absolute path):

```sh
time /absolute/path/dagger-collections-perf/bin/dagger \
  --engine container://dagger-engine.collections-perf-normal check -l --all
```

The first command populates the new engine cache. Repeat for warm timings;
then change an application file and immediately run again for edit latency.
Keep telemetry enabled and verify all 14 listing rows, not only exit status.
The timings in our reports include CLI shutdown. Our broken SSH agent was
omitted symmetrically; there is no reason to disable a working agent locally.

For a pinned reproduction, the measured app is
[`kpenfound/greetings-api@14d684f`](https://github.com/kpenfound/greetings-api/commit/14d684fccf75a137de96f3f0c7eb8c6dafef2d3e)
and its Go collections module is
[`dagger/go@1784ff3`](https://github.com/dagger/go/commit/1784ff37eb3dd1aacab7aaff91b1d86e311cc8de).
That Go commit already bypasses `go-include` for listing. The normal-mode audit
preserves the remote module declaration and records the resolved lock file.

The separate Go existence-check change is available as
[`grouville/go:perf/discovery-existence`](https://github.com/grouville/go/tree/perf/discovery-existence)
and as a [mail-format patch](collections-qa-performance-data/next/go-existence/go-module.patch).
It removes sorting merely to test whether a module owns any files. It improves
the larger synthetic fixtures; it did not demonstrate a gain on greetings-api.
It is not part of the normal-mode audit or a dependency of this engine branch.

## Compare fairly

Build the unmodified `175dca0` engine and CLI in a separate checkout, with a
different image/container/volume name, and run the same app, lock file, engine
flags, and command. Warm both sides before alternating five measured rounds.
Collect wcprof separately with `hack/bench-artifact-discovery.py --wcprof-url`;
profiling runs are not included in latency medians.

Kyle reported 29.88 s cold and 3–4 s warm. We do not have his CLI build ID or
cache-reset procedure. Our control is built from the public PR source, not
verified as his installed binary. An empty engine-cache volume with an
already-ready engine is our cold boundary; host and upstream caches remain.
Recent cold candidate runs failed on `cgr.dev` HTTP 500 and cannot establish a
new cold speedup.
