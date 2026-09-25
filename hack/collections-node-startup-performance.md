# Collections discovery: TypeScript startup caches

September 24, 2026. The target is still **500 ms for the complete CLI command**,
including startup, output and shutdown, with correct source invalidation.
The latest direct comparison is **2.905 s → 2.586 s** median for Kyle's
`dagger check -l --all`: 319 ms / 11.0% faster, still 2.086 s above the target.

## Application and comparison

The application remains `kpenfound/greetings-api` at
`14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`, with the Go module pinned to
`1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. Every listing includes the same
14 checks, configured backend Go base, Playwright service, and SDK generators.

Both variants use the preceding engine stack, including schema-decode commit
`5f7989b041`, experimental Dang syntax caching, split TypeScript imports, and
the prebuilt TypeScript SDK runtime. The CLI and engine executables are
identical between variants. Only the packaged TypeScript SDK runtime changes.
These are not timings of Kyle's unmodified branch or of a normal branch build.

Each timed sample starts a new CLI/session against a warmed engine. Telemetry
remains enabled and CLI exit is included. No Cloud engine/result cache is used;
this does not mean that CLI telemetry has no network exporter. The broken SSH
agent variable is omitted symmetrically. Builds, tests and profiles run outside
timed series. Execution order alternates within each five-pair series.

| Series | Control median | Candidate median | What changes |
| --- | ---: | ---: | --- |
| Transform cache | 2.868 s | 2.622 s | Direct Node loader + persistent tsx transforms |
| Add Node compile cache | 2.713 s | 2.499 s | Also persist Node's compilation cache |
| Direct combined comparison | 2.905 s | 2.586 s | Previous stack → both changes |

Use the last row for the combined gain. Do not add improvements from different
series or present the fastest individual run as normal latency. In the direct
comparison, all five corresponding pairs favor the candidate. Raw values,
host pressure samples and output are retained in the evidence directory.
The direct series has 9.82% CPU some-pressure and 0.20% full I/O pressure;
work itself can create pressure. Each series starts after ten seconds below
5% CPU some-pressure and 2% full I/O pressure.

## What the prototype changes

The SDK currently launches `tsx` for each TypeScript module process. Its bundled
version, 4.15.6, caches transformed source under `/tmp/tsx-<uid>`. That directory
is otherwise lost between executions. This differs from Node's separate cache
of V8 compilation results; our earlier Node-cache experiment did not preserve
these TypeScript transformations.

The prototype:

1. Invokes Node directly with tsx's existing loader, supplying the existing
   tsconfig through `TSX_TSCONFIG_PATH`. This removes tsx's CLI parent process.
2. Mounts a Dagger `CacheVolume` at `/tmp/tsx-0` for transformed source.
3. Mounts a second cache and sets `NODE_COMPILE_CACHE` for Node compilation.

Skipping the CLI wrapper also matters for correctness: that wrapper puts a
PID-derived IPC socket in the same temporary directory. Different container
PID namespaces can reuse a PID, so simply sharing this directory while keeping
the wrapper is unsafe. Direct loader operation does not create that CLI socket.

These are compiler caches, not saved listing output or module execution results.
The bundled tsx implementation hashes source text, transformation options,
esbuild version and tsx version. Node owns validation of its compilation cache.
Changed code is still read, hashed and executed; Dagger result-cache policy,
workspace freshness and `disableDefaultFunctionCaching` remain unchanged.
Empty or evicted compiler caches must produce the same program.

For N invocations, repeated transformation/compilation work moves toward one
pass per distinct source/options/version combination. Each invocation still
reads and hashes source, initializes Node and evaluates the JavaScript module.
This does not make startup O(1), eliminate interpretation, or cache arbitrary
user code's effects. The caches are advisory local Dagger volumes; this gain
does not depend on distributed result caching.

## Profiles and the remaining gap

Separate wcprof captures contain no dropped events or open operations. The
first before/after capture changes the two overlapping TypeScript processes
from 1.019/1.071 s to 0.850/0.852 s. Adding Node caching in a later capture
changes them from 0.804/0.804 s to 0.758/0.769 s. These overlap: their durations
cannot be summed into command savings. Full-command medians are above.

The combined candidate's separate 2.610 s profiled command spends:

| Boundary | Duration | Relationship |
| --- | ---: | --- |
| Initial `Workspace.artifacts` | 1.123 s | Loads modules and discovers static artifact paths |
| `Artifacts.__itemsJSON` | 0.820 s | Expands collections after that first phase |
| Later `Workspace.artifacts` | 0.060 s | Metadata used to render dimension flags |
| All recorded engine operations, first to last | 2.047 s | Includes these phases; not an additional cost |

The difference between CLI duration and the recorded engine span is 563 ms in
that capture. It includes unprofiled boundaries, not just telemetry. A separate
CLI CPU/execution trace attributes **320 ms of blocked time specifically to
tracer-provider shutdown**; logger and meter shutdown are negligible there.
That is measured waiting, not a configured 320 ms sleep.

A separate Node CPU probe imports the actual greetings-api SDK and frontend
inside the same Node 24.13.1 image. With both caches warm, imports still take
about 243 ms and the instrumented process spans about 445 ms. This is a small
profiled diagnostic, not the CLI benchmark. It shows remaining module evaluation,
loader-worker coordination and startup even after compilation-cache hits.
Main-thread and worker profiles overlap and must not be added. In particular,
`makeSyncRequest` samples include waiting for the loader worker, not exclusively
CPU doing useful computation.

To reach 500 ms, the next changes must remove whole phases:

- Avoid starting user-language runtimes to describe modules. The static SDK
  entrypoint work already being pursued is directly relevant; this experiment
  does not replace or duplicate that architecture.
- Reduce declaration/type-graph reconstruction and the serial boundary before
  collection expansion. Loading an unrelated frontend currently delays Go
  collection discovery. Pipelining needs shared module-loading synchronization,
  global ambiguity checks and dimension aliases preserved; merely launching
  more CLI requests is not sufficient evidence of a valid implementation.
- Avoid constructing configured execution containers just to obtain collection
  keys where the module does not use those containers for discovery. Preserve
  configured service bindings, caller authority and error semantics when
  introducing deferred resolution.
- Reduce the CLI's final synchronous export boundary while retaining delivery
  guarantees. Disabling telemetry or returning before events have a durable
  owner would not satisfy this benchmark's requirements.

These are identified targets, not measured future savings. No 500 ms result
has been obtained, and independent cache gains cannot establish that result.

## Edit and runtime correctness

All 30 measured warm listings match the expected output byte for byte.
The transform-only and combined variants each pass 12 paired edit validations:
comment changes, renamed/added tests, a new Go module, and restoration. Expected
keys are computed independently, and complete output is compared across engines.

| Direct combined comparison after edit | Control | Candidate |
| --- | ---: | ---: |
| Comment only | 2.902 s | 2.589 s |
| Rename test | 2.888 s | 2.634 s |
| Add test | 3.155 s | 2.566 s |
| Add module | 3.094 s | 2.941 s |
| Restore | 2.803 s | 2.551 s |

These are one observation per edit, not distributions. They do not establish a
universal per-edit improvement. All source files are restored in `finally` blocks.

Both prototypes also execute the real frontend `build` function with the
original and split SDK bundles: original output, a function-body change that
returns a unique marker file, an intentional error, then restoration. All 16
calls return the expected value or error. This checks runtime invalidation,
not just unchanged listing names. It does not run the application's entire QA
suite or claim faster test execution.

Focused existing TypeScript integration cases also pass with a freshly built
`core/integration` test binary: syntax/default arguments, telemetry import, and
execution-error surfacing. This includes generated entrypoint execution. The
complete SDK compatibility matrix remains outside this validation.

## Cold behavior and upstream status

First population of the two new Dagger volumes took 33.416 s and 26.418 s.
These are unpaired setup observations. Both include compiler-cache misses, and
the prototype packaging adds a replacement runtime binary as another OCI layer.
They are not a controlled cold comparison and do not demonstrate a cold gain.

The [combined patch](collections-qa-performance-data/node-startup/runtime-node-caches.patch)
is committed as an experiment; a normal source build does not enable it.
Its default Node 24.13.1/root-user path is exercised here. Before enabling it:

- Preserve compatibility with supported older Node versions and custom images:
  `--import` is not available on every version accepted by tsx. Select a supported
  loader path or retain the previous launcher outside the validated range.
- Derive or constrain the transform-cache location for the image's effective UID
  and temporary-directory settings; do not assume `/tmp/tsx-0` universally.
- Exercise ESM/CommonJS, generated and committed entrypoints, cancellation,
  source-map/error locations, concurrent executions and cold/evicted caches.
- Keep transient IPC outside any shared compiler cache. Namespace compiler
  caches deliberately, and retain normal Dagger cache lifecycle/GC behavior.
- Build the SDK source and prebuilt SDK executable together. Applying only an
  engine binary or changing SDK source without rebuilding its payload will not
  activate this change.

The [evidence directory](collections-qa-performance-data/node-startup/) includes
all three alternating series, output, edit/runtime checks, scripts, profiler
summaries and hashes of the executables and raw profiles. The baseline remains
reproducible through [the performance start guide](collections-performance-start.md).

All three isolated benchmark engines are stopped with exit code zero; their
cache volumes are retained. Engine shutdown is outside the CLI timings.
