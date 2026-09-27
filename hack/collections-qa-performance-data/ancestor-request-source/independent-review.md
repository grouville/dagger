# Independent source review: explicit parent metadata

Reviewed source and tests read-only; no engine/CLI command or additional build was run by this reviewer. The candidate is suitable for the bounded local runtime experiment. It is not yet a claim of cross-platform or full-command performance improvement.

## Compatibility and authority

`ParentDirsOnly` is an additive, omitted-when-false JSON field. `LocalImportOpts` still emits the original source root plus exact include and exclude metadata; a prior JSON decoder ignores the unknown field and follows the existing filtered traversal. A new client paired with an old engine receives no flag and follows that same path. A forwarding client that drops the flag also retains a correct slower fallback. No old packet type or file-request ID contract changes.

The engine enables the operation only inside `syncParentDirs`, after the existing StatResolvePath RPC returns the import path. Root, metacharacter, negated, escaped and unclean targets remain on the original request. The actual subtree import is unchanged. The client validates the exact single include/exclude pair, rejects git-ignore/follow-path and other special modes, and requires the resolved request root to be the filesystem/volume root. `NewParentMetadataFS` checks host-native `filepath.IsLocal` and cleanliness and cannot serve file contents. This does not expand the session's local read authority or authorize arbitrary filters to become unfiltered reads.

## Point-lookup contract

This is explicitly a point-metadata operation, not an implicit replacement for generic NewFilterFS. It uses the native filesystem's path spelling/case rules and performs fresh stat reads. Execute-only ancestors can yield metadata where the old directory enumeration could not list entries; that is a deliberate operation-contract difference within the same OS/session authority. Directory-block errors observable only during enumeration are outside the new point operation. Generic filtered imports retain their old behavior.

The requested directory chain is first validated completely. Missing, symlink, regular-file or inaccessible components fail before initial emission. Root metadata is checked but is not itself sent, matching the parent stream shape. The existing filter still handles ordered parent emission and metadata mapping. Emission-time Info refresh can fail if paths change afterward. The enclosing existing NewFilterFS converts ENOENT/ENOTDIR into SkipDir, which the helper treats as successful termination; such a race may therefore yield an empty or partial successful stream. The strict failure guarantee applies to preparation-time validation, not every later mutation. Other callback errors still propagate. This is not an atomic filesystem snapshot. Subsequent operations retain fresh checks and no cross-call metadata cache.

A symlink supplied by the user is resolved by the earlier StatResolvePath flow; a symlink observed by the chain’s own Lstat/Info is rejected. These are path-based syscalls: an ancestor replaced between syscalls can still be traversed, as in the ordinary walker. This is not an openat/no-follow descriptor-based guarantee against concurrent hostile replacement. This is the correct division of responsibilities. The unchanged general mirror apply still walks its engine-local parent state; this prototype primarily removes sender-side enumeration and does not claim both sides are now bounded.

## Tests and remaining gates

The helper tests explicitly construct NewParentMetadataFS, so there is no silent legacy-versus-legacy comparison through a platform gate. They cover normal directory stats/map ordering, fresh metadata, missing/replaced/symlink paths, cancellation, SkipDir and stat-count growth independent of siblings.

The actual FilesyncSource.DiffCopy test builds incoming gRPC metadata from ToGRPCMD, asserts the flag survived decoding, then verifies normalized ordered directory-only packets. The missing-target dispatch witness must produce an error packet; that distinguishes the new dispatcher from the legacy empty stream. Invalid mode combinations, escaping targets, non-root requests and extra/reincluded exclusions are rejected before streaming. This is an in-memory service-stream test, not a network transport compatibility test against an independently built old binary. The additive wire-structure test complements it; a bounded mixed-binary runtime check remains useful if needed.

Windows source handling is appropriately split: wire patterns remain slash-separated, client FromSlash converts the helper target, and host-native IsLocal/root checks enforce drive/volume semantics. The test helper was adjusted to use native separators. No Windows execution was performed, so drive-letter, UNC and reparse-point integration remains an upstream test gate; do not call Linux success a Windows validation. Existing snapshot path canonicalization is outside this patch.

## Next separate opportunity

The current import still waits for three serial steps: resolve/stat RPC, parent metadata RPC, then subtree stream. Removing sibling enumeration does not remove those round trips. A future protocol could return the canonical root and ancestor metadata at the front of one subtree stream, preserving source resolution, directory-only parent normalization, ordered diff IDs, cancellation, receiver readiness, and old-client fallback. That requires a separate versioned contract and latency attribution, especially on remote engines; it is not included in the present timing comparison.
