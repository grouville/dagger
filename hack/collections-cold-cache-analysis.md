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
   The two app builds dominate the stable cold path. Portable generated schema
   metadata or narrower module loading could avoid work even without a peer;
   either needs semantic and invalidation validation before implementation.
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

The retained code change is finer layer-level wcprof instrumentation, validated
by five focused snapshot tests and complete listing profiles. No new speedup
is attributed to that instrumentation. The trimming and pipelined-hashing
experiments remain disabled.

Evidence, repeat scripts, timings, output, compact host samples and raw-profile
hashes are in [go-import/](collections-qa-performance-data/go-import/), especially
`variance/` and `historical-host-metrics.json`. The historical metrics and
quarter-second samples have different time resolutions; comparisons above
state which is used.
