# Cold collections discovery: variance and distributed caching

September 24, 2026. Command: `dagger check -l --all`, with the complete
`kpenfound/greetings-api` configuration, including the backend Go base and
Playwright service settings. This follows the [Go image investigation](collections-go-import-performance.md).

**Distributed caching can avoid repeated compilation when another engine has a
compatible result. It does not make every cold start warm.** The other finding
is that our slow cold samples coincide with substantial host disk pressure.
We should optimize the work and report that pressure alongside latency.

## Measurement scope

These runs use the experimental stack: engine/CLI improvements, Dang syntax
cache, split TypeScript imports and prebuilt TypeScript SDK runtime. They keep
the original Go SDK image and remote Go module. They are not timings for a
normal build of the branch without those prototypes.

App: `14d684fccf75a137de96f3f0c7eb8c6dafef2d3e`; Go module:
`1784ff37eb3dd1aacab7aaff91b1d86e311cc8de`. The engine executable and CLI are
identical in every cold sample discussed here. Cold means a fresh empty Dagger
volume on an already-ready engine. Engine provisioning, host page-cache reset
and engine-image download are outside the measurement. No Cloud cache is used.
All timings include CLI exit. All listings match the expected 14 rows byte for
byte; cold wcprof captures have no dropped events or open operations.

## Why 27.27 s became 45.13 s

The profiles localize the slowdown beyond image extraction:

| Operation | 27.272 s sample | 45.134 s sample |
| --- | ---: | ---: |
| Copy bundled Go SDK compressed blobs | 0.799 s | 4.932 s |
| Extract Go SDK root filesystem | 4.445 s | 4.799 s |
| First application-module Go build | 10.794 s | 12.390 s |
| Second application-module Go build | 5.346 s | 10.336 s |
| Late runtime call, including image metadata resolution | 2.656 s | 5.886 s |

These spans overlap other work and do not partition total command latency.
The bundled-image copy reads local engine-image files; it is not a download
from `registry.dagger.io`.

An existing benchmark engine had retained about 14.6 GiB resident memory and
2.83 GiB swapped memory with no active sessions. Its periodic host metrics
also cover the original runs:

* The first profile starts at 19:10:25 UTC. Host CPU iowait in the one-minute
  interval ending 19:11:14 is 0.72%.
* The slower profile starts at 19:12:33 UTC. The interval ending 19:13:14 has
  30.83% iowait and only 17 MiB of unused swap.

Those intervals are coarser than the commands. They establish concurrent disk
pressure, not an attribution of all 17.861 extra seconds to a particular
process or proof that the old engine caused it. High swap occupancy alone
also does not establish active swapping.

The idle benchmark engine was stopped, retaining its volume. It exceeded its
60-second shutdown deadline and Docker stopped it with exit 137. Subsequent
runs started after it exited; this was an environment intervention, not a
performance code change.

Three further new-volume runs sampled `/proc` every 250 ms while recording
wcprof. No engine builds or tests ran alongside them:

| Sample | Full listing | Host CPU iowait | Host I/O pressure, full stall | Swap in / out |
| --- | ---: | ---: | ---: | ---: |
| quiet-0 | 28.631 s | 1.20% | 0.397 s | 38.55 / 41.56 MiB |
| quiet-1 | 26.091 s | 0.78% | 0.246 s | 0.64 / 5.72 MiB |
| quiet-2 | 32.984 s | 14.40% | 8.566 s | 0.54 / 0.07 MiB |

The sampler covers the benchmark driver and profile dump, slightly beyond the
timed CLI. Linux PSI full I/O stall is a host pressure measure, not time charged
directly to this command. The third sample has at least 39.6 GiB available
memory and negligible swap traffic: memory occupancy cannot explain all the
variation. Its root NVMe device records about 199 MiB read and 911 MiB written,
with 17.1 s of device busy time during the sampled interval. Buffered writes
and a growing I/O queue coincide with the slower late image-resolution calls.
The evidence does not yet distinguish their disk waits from network latency.

Afterward, five warm, unprofiled listings give a median of **3.107 s** and a
range of **3.060–3.617 s**. They also all match the complete output. Stopping
the old engine did not produce a substantial new warm improvement.

## What the in-flight distributed cache covers

The measured branch already includes the value-transfer and lazy-acquisition
foundation from [#14228](https://github.com/dagger/dagger/pull/14228),
[#14229](https://github.com/dagger/dagger/pull/14229) and snapshot sharing from
[#14235](https://github.com/dagger/dagger/pull/14235). Their presence is not
evidence that this local benchmark fetched results from another engine.

The newer stack, merged September 24 and absent from the measured executable,
adds [cache facts (#14300)](https://github.com/dagger/dagger/pull/14300),
[fact export to Cloud (#14301)](https://github.com/dagger/dagger/pull/14301) and
[remote identity entries (#14302)](https://github.com/dagger/dagger/pull/14302).
These let Cloud discover equivalent results on other engines. A remote entry
contains identity and dependencies, not a usable value; ordinary value lookups
explicitly skip it. Fact export is opt-in. The index needs the transfer,
acquisition and deployed integration paths to produce a real remote cache hit.

The following is a code-based prediction, not a measured Cloud speedup:

| Measured work | Cold local engine, usable result on a peer | No usable result anywhere |
| --- | --- | --- |
| Application-module compilation: about 16 s across two builds in the stable samples | A compatible completed result could replace compilation with acquisition | Compilation still runs |
| TypeScript SDK/module preparation and dependency installation | Compatible outputs can be reused, with required files acquired lazily | Preparation and installation still run |
| Go SDK root filesystem import: about 4.2–4.7 s in the new samples | Can disappear if no demanded output needs it; required missing layers still need applying | Still paid when the SDK is needed |
| Source identity and caller/workspace authorization | Must still establish that reuse is valid | Must still establish identity and authorization |
| Mutable image-tag resolution and explicitly non-cacheable module calls | A peer does not authorize treating these as immutable cached answers | Still run |
| CLI startup, listing coordination and shutdown | Remote reuse does not by itself remove them | Still run |

The local app's Go module configurations explicitly set
`disableDefaultFunctionCaching = true`. This does not disable ordinary cacheable
build operations, but we cannot assume that every module function answer becomes
reusable simply because a peer has seen it. Those settings remain unchanged.

There is a concrete materialization constraint: the
[Go SDK runtime builder](../core/sdk/go_sdk.go) returns the built SDK container,
removing cache mounts but retaining its compiler filesystem. The transfer path
in [ImportChain](../engine/snapshots/import.go) calls the same `importLayer` used
by ordinary image imports. Downloading a completed runtime can avoid its build
while still requiring compiler/base layers to be extracted on a new engine.
Lazy part acquisition avoids unneeded parts; it does not automatically turn a
whole filesystem into independently fetched files.

Thus there are three distinct benchmarks to retain: empty local and empty
remote cache; empty local with a populated compatible peer; and warm local.
Only the first local condition and warm local have been measured here. No
distributed-cache latency or predicted percentage is claimed.

## Where further optimization should go

1. **Reduce compilation required just to discover module definitions.** Go
   currently obtains definitions by building and invoking the module runtime.
   The two app builds dominate the stable cold path. Existing manifest-v2
   entrypoints already support a separate type path; test SDK adoption before
   adding a new mechanism (see the SDK review below).
2. **Measure a real peer hit before optimizing around it.** Check compilation
   count, transferred bytes and layers actually applied, as well as command
   time. Repeat after changing source and verify that stale results never win.
3. **Reduce demanded runtime contents without losing shared layers or tools.**
   Removing compiler test files was rejected because it lost reuse with the
   application's Go image. A compact execution stage would need to preserve
   runtime capabilities; deleting files in a final layer does not avoid
   extracting its parent layers.
4. **Separate image-resolution network time from local metadata I/O.** The
   slower late `Container.from` calls are the remaining variance boundary.
   Keep normal tag freshness and credential isolation when optimizing them.

## How to avoid compilation for definitions

A follow-up source audit makes the first item more specific. The builtin Go
SDK's `AsModuleTypes` returns false. `moduleSourceAsModule` loads dependencies,
then `moduleDefViaRuntime` asks for the Go runtime. Building that runtime runs
`go build`; invoking its dispatcher with an empty object name returns the
module's declarative registration expression from `dagger.gen.go`.

The two application modules have different requirements:

| Module | Why the listing loads it | What a static definition could avoid |
| --- | --- | --- |
| `greetings` | Its workspace entrypoint schema must be known; the generated API has `Build` and a constructor | Its compilation for definition discovery; the second Go build is about 5 s in the stable profiles |
| `backend` | Its schema is needed, and `base = "dag://backend/go-test-base"` also invokes its code | Definition discovery can become cheap, but the configured base still requires a runtime under the current argument-resolution path |

Therefore a schema-only change cannot be assumed to remove the full 16 s of
Go compilation. Deferring a required build can also change overlap with other
work. A full-command benchmark must measure the resulting critical path.

The existing generated registration expression is 726 bytes for `greetings`
and 3,046 bytes for `backend`. A diagnostic parses the full generated Go files
in memory and finds this expression: median 0.155 ms and 0.232 ms, respectively,
over 1,000 iterations. This excludes file I/O, input validation, schema
installation and the entire Dagger command. It demonstrates that the definition
itself is small; it is not an implemented fast path or a predicted latency.
The diagnostic is intentionally not an authoritative schema loader.

## Existing SDK work: use ModuleEntrypoint

The SDK PR review changes the implementation direction: **do not add another
portable-schema format.** The common `ModuleEntrypoint.types` / `call` interface
already exists, and the benchmark branch already includes its engine loader
from [#14038](https://github.com/dagger/dagger/pull/14038). `entrypointSDK`
implements `AsModuleTypes`; its type path calls `EntrypointModuleTypes`, while
its runtime is a separate Dang entrypoint call. An entrypoint may compute its
types dynamically, so the interface alone is not proof of cheap discovery.

The SDK authors own this implementation work. This investigation leaves it to
them and moves to independent bottlenecks. The subsequent
[archive parent-path experiment](collections-extraction-parent-performance.md)
tests one such optimization; its small import gain does not establish faster
complete discovery, so it remains disabled.

Yves Brissaud (`eunomie`) already contributed the related SDK lifecycle work:

* [#13381](https://github.com/dagger/dagger/pull/13381), Go no-codegen-at-runtime
  and single-pass generation, is in the benchmark branch. The generator derives
  self-call types without first building the module, but the builtin Go runtime
  still builds the module to load its definition.
* [#13598](https://github.com/dagger/dagger/pull/13598) makes the rule generic:
  TOML modules use committed bindings, and SDK capability detection permits
  omitting dependency introspection from runtime construction. It is also
  already included, along with Python adoption in
  [#13593](https://github.com/dagger/dagger/pull/13593).
* [#13548](https://github.com/dagger/dagger/pull/13548) already loads selected
  workspace modules on demand. Complete listings still need all candidate
  definitions. It too is included.

The newer SDK implementations provide the more direct match:

| SDK work | Actual discovery path in the reviewed code | Status on September 24 |
| --- | --- | --- |
| Yves's [Java SDK #19](https://github.com/dagger/java-sdk/pull/19) | The annotation processor renders static Dang TypeDefs from the same model as runtime registration. `types()` returns them; `call()` requests the jar build. | Open prototype |
| Solomon's [Go SDK #36](https://github.com/dagger/go-sdk/pull/36), referenced by the Java PR | Generates static Dang TypeDefs and a separate `call()` that requests the Go dispatch binary. | Open prototype; not automatically applied to the benchmark app |
| Yves's [Python SDK #33](https://github.com/dagger/python-sdk/pull/33) | The shared entrypoint's `types()` requests `describeJSON`, which uses `build.installed` and runs `python -m dagger.mod describe`. | Open; the shared entrypoint still prepares and imports Python code for discovery |
| Yves's [Go SDK #35](https://github.com/dagger/go-sdk/pull/35) | Offers an opt-in build-only runtime and moves generation into the SDK repository; the runtime still compiles committed Go source. | Open; leaves builtin `go` routing unchanged |

These findings come from the implementations, not only the PR titles. In
particular, no-codegen-at-runtime is already achieved on our TOML baseline;
no-compilation-for-type-discovery is a different property. Python's earlier
AST analyzer was deliberately removed in Yves's
[#13251](https://github.com/dagger/dagger/pull/13251), returning to runtime
introspection. A second universal source scanner would duplicate language
semantics and undo that direction.

Both application Go modules in our measured greetings-api checkout still say
`[runtime] source = "go"`, rather than selecting a generated Dang entrypoint.
That explains why our cold profiles still contain their two builds despite the
engine supporting the newer interface. Go SDK #36 also currently rejects
`package main`, which these modules use; trying it requires an isolated,
explicit migration rather than silently calling it the same baseline. Its
older PR description says the engine loader is unfinished, but #14038 has
since merged and is already in this branch. Its generated `call` still takes
`fnArgs: [FunctionCallArgValue!]!`, whereas the merged engine contract takes JSON. That protocol mismatch and the package
layout must be adapted before an honest end-to-end comparison; merging the
engine loader alone does not make this older prototype compatible.

The next performance experiment should therefore use the existing entrypoint
protocol: migrate an isolated copy, compare the complete listing and metadata,
then exercise actual calls and edits. Count builds separately under `types()`
and `call()`. For Python, distinguish its shared entrypoint from an SDK-generated
static entrypoint. Preserve defaults, check and collection annotations, source
maps, invalidation, services and caller/workspace authority. No new schema file
format or engine loader is needed merely to test this direction.

The custom Go base still calls `backend/go-test-base` during the current listing
path, so cheap type discovery alone does not make every runtime unnecessary.
Deferring execution-only settings, without changing their Container API or
per-call semantics, would be a separate experiment. This review does not claim
new full-listing timings or that the prototypes are ready to merge.

The [definition audit](collections-qa-performance-data/go-definition/)
contains the standalone size/parsing diagnostic, results and a pinned PR/source
ledger. It is not a production loader. No engine behavior changed in this audit.

The retained code change is finer layer-level wcprof instrumentation, validated
by five focused snapshot tests and complete listing profiles. No new speedup
is attributed to that instrumentation. The trimming and pipelined-hashing
experiments remain disabled.

Evidence, repeat scripts, timings, output, compact host samples and raw-profile
hashes are in [go-import/](collections-qa-performance-data/go-import/), especially
`variance/` and `historical-host-metrics.json`. The historical metrics and
quarter-second samples have different time resolutions; comparisons above
state which is used.
