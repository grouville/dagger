# Share the mount used to validate package digest paths

Keep this experiment unselected. Sharing a stat mount reduces a fully prepared 1,026-path digest request from **24.3 to 18.5 ms**, but the complete edited-command comparison does not establish a useful gain. The prototype duplicates path-validation code for a small saving. No upstream proposal is added.

The selected engine's large-check profile showed 55 ms in `Directory.digests`. Its resolver calls `DigestPath` separately for each package: snapshot/path evaluation, a stat mount and content-hash lookup. The prototype evaluates the parent once and keeps one read-only mount across the batch. It preserves the existing hash format, symlink handling, input order, repeated paths and errors. Single-path and empty requests retain the original implementation.

The existing snapshot implementation already shares immutable mounts. The remaining per-path mount cost is therefore much smaller than a new filesystem mount for every package.

## Results

Six alternating component pairs use fresh parent directories and prepare their source/checksum state outside the timer. These are requests through the real engine, including query and response handling.

| Paths | Original | Shared mount | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.841 ms | 1.858 ms | 0.015 ms | 3/6 |
| 130 | 5.061 ms | 4.448 ms | 0.649 ms | 6/6 |
| 1,026 | 24.280 ms | 18.469 ms | 5.736 ms | 6/6 |

Eight balanced randomized pairs per complete workload use the same physical source, Rust module `da1ae47`, compiler history and diagnostic engine. Every command has a fresh source edit and CLI process. Engine/compiler caches are warm; telemetry and ordinary collection stay enabled. Both selected artifact string-getter policies remain enabled in both arms. Wcprof is off during timing; no GC is forced.

| Complete edited command | Original median | Shared mount median | Cargo median | Median paired saving | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Collection check, 1,026 crates | 1.455 s | 1.429 s | 0.760 s | 18 ms | 5/8 |
| Direct check, 130 crates | 0.629 s | 0.629 s | 0.127 s | 19 ms | 5/8 |
| Small workspace tests | 1.007 s | 1.023 s | 0.486 s | 13 ms | 5/8 |
| Expanded listing, 1,026 packages | 2.544 s | 2.560 s | 0.437 s | −1 ms | 4/8 |

Column medians and paired differences differ. All admitted observations are retained, including host memory pressure reaching 16.9% during a large check and I/O pressure reaching 24.7% during a direct check. Listing CPU pressure reaches 29.4%. These conditions and the mixed pairs prevent a strong latency claim.

Separate wcprof captures complete without dropped events or open operations. The large check's digest resolver takes **65.5 → 44.1 ms** in that diagnostic pair. This confirms less local work, but does not replace the complete-command comparison.

## Correctness and disposition

Both modes pass **42 compatibility cases**, including 18 error cases. Constructed and host-imported directories cover nested selections, parent-relative paths, permissions, Unicode and quoted names, directory and file symlinks, missing paths, broken links, loops, ordered duplicates and empty batches. Expected digests and success/error behavior come from the existing `directory(path).digest` operation.

The engine exits cleanly before installation and retains its volume. The candidate is reversible and disabled after measurements. Compiler recipes and the Rust module are unchanged. This experiment adds no upstream proposal.

[Raw commands, compatibility probes, profiles and source manifests](experiments/digest-paths-mount/) preserve the prototype for review. The broader performance goal remains active; a smaller local mount gain does not resolve the remaining import, discovery, compiler-orchestration or listing costs.
