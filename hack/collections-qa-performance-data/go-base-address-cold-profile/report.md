The two fresh-volume wcprof diagnostics isolate the cold improvement in collection expansion. Catalog construction and both Go module runtime builds remain almost unchanged. These are instrumented observations, separate from the four ordinary cold samples.

| Profile boundary | Original `base` | Opt-in `baseAddress` |
| --- | ---: | ---: |
| Catalog, `Workspace.artifacts` | 20.366 s | 20.319 s |
| Expansion, `Artifacts.__itemsJSON` | 3.238 s | 0.427 s |
| Go runtime compilation, two process intervals, union | 14.616 s | 14.572 s |
| Backend constructor, executed body | 87.7 ms | Absent |
| Backend `goTestBase`, executed body | 2.563 s | Absent |
| Total process intervals | 15 | 13 |
| Open / dropped operations | 0 / 0 | 0 / 0 |

The original `goTestBase` method spent 2.474 s in ten nested engine queries. Three `Container.from` resolver intervals covered a 2.454 s union; their inclusive sum was 3.780 s because they overlap. The method's process interval was 2.551 s, while its recorded `exec.containerStart` phase was 0.397 ms. This attributes most of this cold producer cost to image/container preparation requested by the method, rather than process startup. It does not separate registry latency, image decoding and local storage within `Container.from`.

That attribution joins wcprof `nested_client` links to the roots of the corresponding client operations. Following parent IDs alone misses the nested engine work. The reducer publishes only fixed operation names and aggregate timings; raw client identifiers and profiles remain private.

Both compilation intervals match the built-in Go SDK's `go build -ldflags -s -w -o /runtime .` command in `core/sdk/go_sdk.go` (`Runtime`, at frozen source `2088d5efed34ccff90829bec502320eeca579fc7`). They are module runtime compilation, not the backend application's `go build -o greetings-api .`. The public fixture configures the backend and greetings modules with `[runtime] source = "go"`. This native profile does not retain the `ModuleSource` receiver/name arguments, so the two individual durations are deliberately not assigned to these names by order.

The previously reviewed Go SDK PR 36 static metadata work addresses a related boundary: exposing schema without first constructing the module runtime. That work is not active in this frozen stack, and our attempted migration of its pinned `4dfd447d58344835a0d4692ec0c8e5683c18bd6f` revision stopped at concrete compatibility failures. No speedup from that migration has been measured. Even with static metadata, actual module behavior still needs its runtime. The Address option removes the producer from listing but does not remove the two observed runtime compilations in this experiment.

Both variants used engine `38711bd2b42e410f9fbf601d4260b47718e8169f7ff1d2caa29313adfba4569c`, CLI `d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8`, identical SDK blobs, the same temporary workspace path and reset original lock. The only module difference was the explicit `baseAddress` option versus the original `base`, using equivalent local module layouts. Each command was the first Dagger invocation on a newly created volume; neither had a primer. Both returned the exact ordered 14 check rows.

The host image, SDK blobs and host page/image caches were retained. Engine provisioning/start, profile download, shutdown and cleanup were measured separately from blocking full CLI exit. The profiled CLI observations were 23.856 s and 20.985 s; they are not included in ordinary benchmark statistics and are not a replicated latency estimate. Every recorded operation lies within its CLI interval. Inclusive phase sums are not additive and the profiles do not attribute the ordinary samples' roughly 87 CPU-seconds entirely to compilation.

Both new containers were removed, then the two exact owned volumes were explicitly removed after evidence capture. Volume cleanup took 1.467 s, outside command timings. The original workspace and all pre-existing engines/volumes were preserved. There were exactly two local commands, zero Cloud commands, no guard failures and no additional Dagger calls for profiling. Raw CLI output, native profiles and volume contents are excluded from the safe archive.
