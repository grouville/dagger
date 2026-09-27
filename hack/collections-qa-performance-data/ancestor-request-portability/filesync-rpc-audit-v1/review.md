# Host import RPC sequence: source audit

The import has redundant serial boundaries, but the current evidence does not attribute 100 ms to network round trips. A successful inner `FileSyncer.Snapshot` starts three DiffCopy streams in order: resolved stat, ancestor metadata, and requested subtree. `Host.directory` also makes an earlier absolute-path RPC, and gitignore root discovery may add further calls. All these streams reuse the selected caller's existing gRPC connection. They are not new Docker tunnels or TCP/TLS handshakes.

The earlier retained local listing profile contains 10 executed `Host.directory` calls, 153.993 ms inclusive and 113.690 ms interval union. Four other `call` events did not execute the resolver. Source therefore implies 30 inner streams plus 10 initial absolute-path requests for those successful imports, before optional gitignore work. This is a source-derived count, not a packet capture. It excludes requested-content messages within each stream. No individual RPC start/receive timers exist in that capture, so neither the aggregate import time nor the 30 streams can be converted into predicted removable RTT cost.

The new explicit-parent profile, reported separately by the runtime owner, reduces parent synchronization interval union from approximately 94.4 to 7.29 ms. Collapsing that remaining stream would remove only its avoidable communication/setup portion, not the metadata/apply work still required. This is now a lower-priority local latency target. A remote engine with meaningful client RTT could benefit more, but that has not been measured here.

## Current boundary and dependency map

| Step | Current source | Why the next step waits |
| --- | --- | --- |
| Initial absolute path | `core/schema/host.go:201`, `engine/engineutil/filesync.go:107` | The engine needs a client-native absolute path for gitignore rooting, workspace lock exclusion, and per-client/drive mirror selection. This does not resolve symlinks. |
| Resolved stat | `engine/filesync/filesyncer.go:79` | The response supplies the canonical import path, including symlink resolution. The engine separates its drive and relative mirror path. |
| Ancestor metadata | `engine/filesync/filesyncer.go:120`, `:140` | A fresh chain is merged into the mirror before `newLocalFS` can open the actual subtree root. It retains change-cache conflict handling. |
| Subtree stat stream | `engine/filesync/remotefs.go:72` | Ordered stats feed the diff against the mirror; the sender's implicit file IDs must agree with the receiver. |
| Needed content | `engine/filesync/remotefs.go:198` | The receiver requests only changed needed files. A warm matching file is not uploaded again. |

`newLocalFS` calls `fsutil.NewFS` on the mirror subtree, which must already exist. Starting an independent subtree consumer before parent apply completes is therefore incorrect. A combined stream could begin producing bounded data earlier, but the engine must apply the prelude before opening and consuming the subtree diff. Existing 128-entry stat queues and demand-driven file transfers should remain bounded; avoid eagerly buffering a complete source tree or file bytes.

## Smallest safe protocol direction

The first viable increment is one request returning a typed canonical-stat/ancestor prelude followed by the existing subtree packet stream. Canonical path and parents are sampled fresh by that same selected host client. The engine validates the prelude, applies parent stats using the existing mirror machinery, then exposes the ordinary subtree packet stream to `remoteFS`. No extra acknowledgement is inherently required before the sender starts the bounded subtree walk. Backpressure handles a receiver still applying its parents.

This needs a negotiated operation, not just another ignored JSON flag. The explicit-parent flag is backward compatible because both versions return the same ordinary directory packet shape. A prelude has a different shape. An old client silently ignoring a new flag would return subtree packets where the new engine expects a prelude. The existing advertised-method capability model (`engineutil.SessionCaller.Supports`, session attachables) can select a versioned method without an extra capability RPC. Older engines/clients retain the present path. The current `Snapshot`/`remoteFS` receives only `*grpc.ClientConn`; the capability must be carried from the already-authorized caller selection rather than opening an unrelated session.

A proxy must forward the negotiated operation and preserve the same originating client authority. Do not advertise a method merely because the proxy implements it if its downstream caller cannot provide it. A fallback after an unimplemented stream is possible but adds a round trip; capability advertisement is preferable.

Parent stats are filesystem/volume-root relative; subtree stats are import-root relative. Their file-ID spaces also differ. Simply prepending parent `PACKET_STAT` records to the current stream would contaminate the subtree namespace and implicit ID counters. A typed prelude or separate section must exclude parent records from subtree file numbering. Retain requested-content messages, error packets, cancellation, and final completion semantics. There should remain exactly one receiver for the underlying stream.

Removing the initial absolute-path RPC is a second, more invasive step: `Host.directory` currently needs that answer before gitignore/filter construction and mirror selection. Gitignore discovery, workspace lock exclusion, Windows drives and UNC paths make passing unresolved user input into a combined request a broader contract. Keep that optimization separate from the first protocol experiment.

## Freshness, permissions, cache invariants

- Resolve and stat on every requested import; do not memoize host metadata across sessions or add a time-based cache.
- Preserve the current client/session selection, stable-client and drive partitioning, workspace read epoch, include/exclude/follow/gitignore rules, `RelativePath`, no-cache option, normalization and content checksum calculation.
- Apply ancestor metadata before subtree mirror access. Preserve conflict/dedup bookkeeping for concurrent imports of overlapping paths.
- Use the same native point-operation contract as explicit parent metadata. Do not silently substitute it for general filtered-directory enumeration.
- One stream narrows a race window; it does not create an atomic host snapshot. Current path-based stat/read operations can observe replacement between calls. Descriptor-rooted no-follow traversal would be a separate security/semantic design, not a claim of this optimization.
- Do not hold a prelude from an earlier call as authority for a later import. If errors or cancellation occur after parent application, preserve the existing behavior that a partial mutable mirror update does not publish a completed immutable snapshot.

## Proof before implementation

Start with separately measured stat receive, parent apply, first subtree stat and last needed-content times. Then compare a negotiated combined-stream prototype against the same native-source bytes on local and controlled remote-latency setups. Test old/new compatibility, proxy capabilities, Windows drive/UNC and symlink roots, directory removal/replacement, changing modes, excludes/reincludes, follow paths, gitignore and overlays, large trees with bounded buffering, overlapping mirror updates, cancellation at every section, and equal resulting snapshot content/digests. Do not alter the ordinary benchmark with artificial latency; use a distinct transport experiment if needed.

No candidate code, new engine, test or runtime call was created by this audit.
