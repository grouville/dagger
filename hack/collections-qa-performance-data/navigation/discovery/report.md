# Current `dagger list -a`: what remains on the warm critical path

This is an offline review of the existing navigation diagnostic, not a new benchmark or a new patch. It uses the retained experimental engine with schema/interface/Dang/TypeScript metadata and pending-source `withFile` changes. The measured command takes **2.337 s**. The source labels below refer to the shared branch; the frozen binary provenance remains in `engine-allocation-round2/navigation-generate-v1/provenance.json`.

| Recorded stage | Interval from CLI start | Duration |
| --- | ---: | ---: |
| Static catalog, `Workspace.artifacts` | 139.7–801.7 ms | 662.1 ms |
| Expanded listing, `Artifacts.__itemsJSON` | 859.9–1553.6 ms | 693.7 ms |
| CLI engine shutdown HTTP | separate CLI clock, after callback | 609.3 ms |
| CLI telemetry close after root end | separate CLI clock, after engine close | 134.0 ms |

The roughly 58 ms between catalog completion and expansion includes request construction, dimension projection/binding and query admission. It is not another 662 ms discovery. Both major artifact calls occur **once**. Combining two HTTP projections cannot eliminate the 694 ms of dependent collection work.

## Four metadata processes still start with warm content

All four have `/runtime` process argv and `ModuleSource.asModule` as their nearest recorded call ancestor. The source path is `runModuleDefInSDK` → `moduleDefViaRuntime` when the selected SDK has no static `ModuleTypes` implementation.

| Registration process | Start from CLI | End | Process duration |
| --- | ---: | ---: | ---: |
| 1 | 189.6 ms | 272.1 ms | 82.5 ms |
| 2 | 202.9 ms | 300.1 ms | 97.3 ms |
| 3 | 305.2 ms | 404.3 ms | 99.1 ms |
| 4 | 492.2 ms | 584.0 ms | 91.8 ms |

Their sum is **370.7 ms**, their interval union **301.5 ms**. They overlap Git and other module loading, so neither number is a predicted recoverable CLI duration. Their source module names cannot be recovered merely from `/runtime` argv or the shared `asModule` label. Converting two local application modules does not establish that all four registration/bootstrap processes disappear.

Two later processes are actual user-module invocations and must be kept separate:

- Backend constructor: 923.3–999.4 ms, **76.1 ms**.
- `Backend.goTestBase`: 1016.9–1097.1 ms, **80.3 ms**.

These construct the configured `base=dag://backend/go-test-base`. The existing `withFile` fix prevents the service binary from building merely for listing. Static schema generation alone does not eliminate these actual functions or permit dropping the configured base.

## Why a warm engine does not make this static catalog free

`ModuleSource.asModule` is intentionally `PerClientInput`. It installs a module whose provenance, settings, source/defaultPath scope and dependency wrappers belong to the current client. Cached build layers and implementation identities can still be reused underneath it, but a previous client's served module cannot replace this authority boundary. With legacy runtime registration, obtaining the definition still starts the runtime even when its binary is already cached. There are 17 asModule calls in this profile, 16 executed, one hit; those are not 16 compiler executions.

`Query.git` discovers implicit caller credentials and visibility. `cachedPublicRemote` singleflights one anonymous advertisement per session and remote, except service-bound cases. `PrimePublicRemote` reuses the same advertisement for ref metadata. The current profile contains seven visibility advertisements and **no `git.lsRemote` phase**. Their inclusive sum is 1112.8 ms, union 439.4 ms, and longest individual probe 439.1 ms. The long probe accounts for most of this profile's union. Re-running in a new CLI session revalidates public access; a commit pin is content identity, not authorization. Removing these probes with a global visibility TTL would alter the existing contract.

Current source/dependency context and collection keys also remain live inputs. Returning keys from a previous invocation would miss real edits. Dagger caches the content-addressed lower operations; it does not assume the workspace, client defaults, access rights or runtime collection enumeration stayed unchanged.

## The substantive next improvement already exists upstream

[Solomon Hykes's Go SDK PR #36](https://github.com/dagger/go-sdk/pull/36), pinned in the earlier review to `4dfd447d58344835a0d4692ec0c8e5683c18bd6f`, emits a Dang entrypoint whose `types(workspace)` describes the schema without launching the Go registration runtime. Its actual `call` builds/runs the Go dispatcher lazily with ordinary Dagger content and compiler caches. **This can help warm as well as cold**: warm removes process starts and metadata RPC construction; cold can avoid building/materializing the dispatcher solely to discover types.

That is a source-level opportunity, not a newly measured speedup. The isolated existing adapter at `warm-audit/go-sdk-pr36-adapter/` reuses the upstream emitter and aligns the JSON argument contract; it is still **unbuilt, untested and unmeasured**. The public PR is an integration prototype, not a drop-in assertion that the current fixture already uses it. Preserve the current source/call/defaults policy and normal generation, then count which processes actually disappear. SDK self-registration or remaining legacy dependencies can keep some processes alive. No duplicate emitter or new implementation is prepared in this audit.

Pinned provenance: `go-sdk-pr36-adapter/provenance.json`; earlier public status refresh retrieved **2026-09-26T08:00:43Z** in `public-pr-overlap-refresh.md`. No new remote request was made for this audit.

## What is and is not a redundant pass

`collectArtifacts` waits for `workspaceTargetModules` to finish. The session loader resolves selected modules concurrently (bounded at eight), then joins all jobs, arbitrates entrypoints, publishes the module batch and releases `modulesMu`. Only then does it build static artifact trees and validate paths. In this profile the final asModule returns only **16.2 ms** before the catalog returns. Parallelizing the tree-formatting tail therefore is not a hundred-millisecond opportunity here.

The CLI then binds dimension flags/aliases and evaluates collection receivers through `Artifacts.Expand`. Expansion already shares prefix resolution and runs independent templates concurrently. It does not evaluate leaf checks. A per-module ready pipeline could overlap discovery with slower unrelated module loading, but the current lock and global validation rules are real constraints: a collection's configured address can demand another module; evaluating it under `modulesMu` can deadlock, and expansion before duplicate-path/global-alias validation changes behavior on invalid requests. See the earlier `list-workspace-reuse/pipeline-review.md`. No small, semantically neutral pipeline patch is claimed.

Aggregate schema setup is now **25.6 ms across 247 schemaBuild phases**, and prepared core forks **3.0 ms across 11 calls**. Metadata-builder micro-optimizations can reduce CPU/allocation, but cannot by themselves remove this 1.4 s engine path. These inclusive figures overlap callers and should not be added to the catalog duration.

A narrower already-prepared scheduling candidate is to start a selected module's SDK load alongside its filtered source-context load, after its authorized config is known and using an immutable source clone. That preserves the canonical Git/auth loader and joins both tasks. It overlaps work rather than deleting visibility checks; it remains untested at `sdk-context-overlap/`. Cold contention and source-kind correctness must be measured before adoption.

`numeric.json` contains only operation labels, relative timings, counts and the wcprof SHA. It excludes argument metadata, result IDs and raw telemetry. `analyze.py` reproduces those aggregates offline.
