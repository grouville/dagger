# Public PR overlap refresh

Retrieved at **2026-09-26T08:00:43.310759+00:00** via read-only GitHub CLI calls. Scope: all 73 open dagger/dagger PRs, the latest 20 created merged PRs for eunomie and sipsma, open go-sdk/typescript-sdk PRs, and specific prerequisite/fix descriptions and file lists. Exact target-file patches were inspected for #14229, #14221, #14317 and #14348. Raw JSON is retained beside this report. No local source, test, engine, Cloud or PR write occurred.

GitHub identifies `eunomie` as Yves Brissaud and `sipsma` as Erik Sipsma. The Eric/SIPS reference was interpreted as Erik Sipsma; the open list contains no separate matching Eric author. This is a scoped overlap check, not proof that no unpublished branch exists.

## Pending-source withFile/withDirectory

**No inspected open PR duplicates the new source-pending condition.** The closest work explains why the remaining bug is a small follow-up:

| Primary source | Current status | Concrete relationship |
| --- | --- | --- |
| [#14288: keep file/service selection lazy](https://github.com/dagger/dagger/pull/14288), Solomon | Merged 2026-09-22 | Fixes Directory.file and Container.asService, including delayed missing-file errors and recipe caching for pending files. Does not touch core/schema/container.go, so it does not fix Container.withFile copying a pending source into a settled destination. Preserve these existing semantics. |
| [#14283: original laziness issue](https://github.com/dagger/dagger/issues/14283) | Closed by the #14288 sequence | Reports the earlier file-selection and service-construction boundaries. Our fresh profile proves the next force at Container.withFile; do not describe the original two fixes as absent. [#14289](https://github.com/dagger/dagger/pull/14289) was an alternate solution closed without merge. |
| [#14229: lazy part acquisition](https://github.com/dagger/dagger/pull/14229), Erik | Merged 2026-09-21 | Supplies retained lazy operations, part acquisition, ownership and delegation. Its exact container schema diff makes mount operations lazy and adds metadata demands, but leaves withFile's destination-only decision intact. Our condition uses its existing ContainerWithFileLazy and cache-side pending predicate, not a second lazy framework. |
| [#14241: remote-cache verification](https://github.com/dagger/dagger/pull/14241), Erik | Open | Tests transfer, acquisition, persisted/pending values and sharing races. Keep its contracts/tests; our new branch should be exercised with restored sources. Its changed-file list does not include core/schema/container.go. Distributed caching does not repair the local eager-source decision. |
| [#14221: collections](https://github.com/dagger/dagger/pull/14221) | Open | Still lists container builds during expanded/key discovery and references #14283. No core/schema/container.go change in its current diff. This gives the narrow fix a directly relatable collections use case. |
| [#14121: squash deep snapshot chains](https://github.com/dagger/dagger/pull/14121), Yves | Open | Prevents overlay mount limits during long edit chains. Changes snapshot manager behavior, not whether a pending producer is evaluated. It adds a bounded chain walk; relevant to separate disk/large-history profiling, not a duplicate lazy-copy fix. |

## SDK/context scheduling

**The proposed overlap is still independent:** after a selected source's config is read, load its SDK alongside filtered context materialization, retaining the exact ordinary loader/auth path and snapshotting before concurrent writes.

- [go-sdk #35](https://github.com/dagger/go-sdk/pull/35), Yves, is open. It moves TOML-module generation into the SDK and adds an opt-in runtime that builds already-generated source. It explicitly leaves engine builtin-Go routing unchanged. This removes codegen/runtime work in its supported path; it does not alter the context-before-SDK ordering in loadConfiguredModuleSource. Reuse that runtime work instead of inventing another compiler pipeline.
- [go-sdk #36](https://github.com/dagger/go-sdk/pull/36), Solomon, is an open manifest-v2 prototype: shared renderer/analyzer, generated dispatch and Dang entrypoint. Its description still says ordinary engine loading of that generated entrypoint is incomplete. It is an integration path for metadata/runtime work, not evidence that SDK scheduling is already fixed.
- [#14346](https://github.com/dagger/dagger/pull/14346), Yves, open, resolves a module's local clients from its own Git/directory/host tree and enforces escape boundaries. Preserve its module-owner provenance when moving work earlier; it intentionally snapshots a host module's tree per call.
- [#14299](https://github.com/dagger/dagger/pull/14299), Yves, open, adds declared-client and Git-commit cache inputs. It touches ModuleFunction dynamic inputs and module identity, not loadConfiguredModuleSource ordering. Do not achieve a scheduling/cache win by omitting those dependencies.
- [#14145](https://github.com/dagger/dagger/pull/14145), Marcos, open, reuses already-loaded dependencies in CurrentModule source APIs. This is direct redundancy removal worth retaining, but distinct from initial source+SDK overlap.
- [#14015](https://github.com/dagger/dagger/pull/14015), Yves, merged 2026-09-09, already removes dead attachables waits, pinned transport probes and duplicate per-client visibility probes. It deliberately retains the first visibility check per session. Our scheduling work must preserve that boundary; no cross-session visibility cache is justified by this PR.

## Telemetry routing/serialization

- [#14189](https://github.com/dagger/dagger/pull/14189), Vito, merged, already deduplicates call-payload delivery per target and switches live subscriptions to negotiated binary protobuf. It does **not** mean ordinary spans are serialized once before local client-store fan-out: the prepared span optimization targets that separate path. Preserve payload ownership/retry and live/final updates.
- [#14317](https://github.com/dagger/dagger/pull/14317), Vito, open, filters reflected subscription resource groups before decoding and stamps only fresh subscription protobuf resources. Exact engine/server/telemetry.go hunks do not alter sessionSpanExporter/clientSpans serialization. Complementary correctness fix, but the shared stored resource must stay unmarked/immutable when implementing serialize-once fan-out.
- [#14348](https://github.com/dagger/dagger/pull/14348), Matias, open, adds an independent engine OTLP destination with bounded queues and destination lifecycle. Its exact telemetry.go changes enrich inbound resources and convert signal data; it does not replace local span fan-out encoding. Do not conflate its asynchronous exporter with faster or lossless local storage.
- [#14349](https://github.com/dagger/dagger/pull/14349), Matias, open, narrows export to selected operation facts/readings. Reuse its operation-data contract rather than introduce another counter system; it leaves ordinary Cloud/CLI signals separate.
- [#14345](https://github.com/dagger/dagger/pull/14345), Vito, open and stacked on archive work, lazily reads/renders retained logs and changes client-store/archive consumers. Its reported memory win is frontend/log-specific. Revalidate row ownership against its store changes; no direct ordinary-span encode-once implementation was found.
- [#14303](https://github.com/dagger/dagger/pull/14303) and [#14341](https://github.com/dagger/dagger/pull/14341), Erik, are merged. They establish engine Cloud publication and endpoint reachability negotiation. These are existing baseline behavior, not gains attributable to a new local store serialization patch.
- [#14287](https://github.com/dagger/dagger/pull/14287), Vito, open, retries admission failures when reading Cloud streams. It is not an ingestion, shutdown, serialization or producer-speed change.

Retain the narrow lazy-copy fixes as separate upstreamable candidates. SDK overlap remains unmeasured; telemetry fan-out remains prepared but uncompiled/unrun. None of the PR descriptions establishes a whole-command speedup for those new candidates.
