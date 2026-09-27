# Explicit parent directory metadata prototype

The initial unit, protocol and race gates pass. The controlled walk benchmark removes dependence on sibling count and also improves the zero-sibling case. All three matched CLI/engine builds succeeded. No full CLI or cold-start result has been measured for this candidate yet.

This replaces one unnecessary operation: `FileSyncer.syncParentDirs` currently asks the host to enumerate from its filesystem root with one literal include and an exclusion for that target's descendants. The filter prunes unrelated subtrees, but still reads and sorts siblings at every ancestor and at the target directory. A host directory import then separately synchronizes the actual requested subtree. Cached Dagger results do not justify skipping fresh host metadata; this prototype obtains that metadata directly instead of enumerating unrelated directory entries.

## Contract and compatibility

The engine opts into an explicit `ParentDirsOnly` filesync request only for the existing canonical, non-root, literal include/exclude pair. Both patterns and the original root remain in the JSON and BuildKit metadata. Old clients ignore the additional JSON flag and run their established filter path. An old engine never sets the flag, so the new client retains its existing behavior. Imports of root or names needing glob escaping initially stay on the old path.

The new client validates the exact filter pair, rejects follow paths, gitignore and all other special modes, requires a filesystem/volume root, and checks the target with host-native `filepath.IsLocal` and clean-path rules. It cannot use the new flag to ignore arbitrary filters or request a wider tree. The same ordinary normalization clears UID/GID/xattrs before transmission. The stream contains directory metadata only; its source cannot open file contents.

This is a point-metadata operation, not an implicit optimization of arbitrary `NewFilterFS` calls. Lookup follows the host filesystem's native case rules and needs normal path lookup/stat permissions; it does not require permission to enumerate each directory or promise to discover readdir-specific I/O faults. No ext-family/casefold ioctl gate is required. These intentional internal operation semantics must be reviewed as such, rather than claiming identical errors to a full directory enumeration on every filesystem.

The complete chain must contain directories before emission begins. A missing component, file, or symlink fails preflight without any directory records. Emission-time `Info` rereads metadata and rejects non-directory replacements. The unchanged outer `NewFilterFS` can convert a late ENOENT/ENOTDIR into SkipDir, however, so a concurrent deletion may leave an empty or partial successful parent stream. Other late errors can fail a partially emitted stream. This retains existing filter race semantics; it is not an atomic host snapshot or a stronger concurrent-adversary containment contract. The actual subtree synchronization still follows, and this source cannot emit file contents. No persistent host cache, TTL, source freshness shortcut, or DagQL cache-key shortcut is added.

## Complexity and measured micro gate

Let d be path depth and w_i the sibling count at each visited level. The old path enumerates and sorts those siblings, with cost depending on the sum of w_i and their sorting. The explicit walk makes d+1 preflight Lstat calls and one fresh stat per emitted directory, plus the existing metadata conversion. It makes no ReadDir calls and its number of filesystem operations is independent of sibling width. Repeated absolute path resolution and string handling still scale with the sum of path-prefix lengths; calling every byte of the implementation strictly O(d) would overstate the claim.

Three 100-iteration samples per case, with fixture construction excluded:

| Siblings at each of four levels | General filter | Explicit metadata | General allocations/op | Explicit allocations/op |
| --- | ---: | ---: | ---: | ---: |
| 0 | 35.08 µs | 15.20 µs | 77 | 62 |
| 100 | 504.02 µs | 16.21 µs | 2,507 | 62 |
| 1,000 | 4,915.69 µs | 15.31 µs | 24,120 | 62 |

The earlier implicit generic-filter prototype needed fresh ext/casefold checks at each ancestor to preserve directory-entry spelling semantics. Its zero-sibling microbench regressed from 32.18 to 47.91 µs. Those numbers come from a separate earlier run and should not be subtracted directly from these samples. They explain why the explicit operation is preferable: it removes both sibling enumeration and the gate that tried to preserve a different API's semantics.

The task host's `/tmp` contains thousands of accumulated experiment entries. That makes the current workload an unusually wide ancestor case. Full CLI measurements must report this fact and must not generalize its saving to every user's small project directory. The saved CLI CPU stacks show directory enumeration is material, but cannot attribute every sender sample to parent synchronization.

## Validation and next matched measurement

Eight normal and eight race test groups cover request validation and additive metadata roundtrip, normal filtered-record/map-order parity, fresh permission-mode metadata, absent/file/symlink components, no content access, held-root replacement, bounded preflight stats, cancellation and callback failures. Actual `FilesyncSource.DiffCopy` tests decode serialized options and send exact directory packets through an in-memory stream; conflicting modes and non-root requests are rejected. The missing-target error packet is a first-divergence witness that the explicit dispatcher was exercised.

A common fixed-label `filesync.syncParentDirs` wcprof operation is compiled into both matched engines. It contains no paths or identifiers and is inactive when profiling is off. It separates parent synchronization from the subtree work in a later profile. Both engines use the frozen f864 SDK/Dang stack and the same source HEAD. The baseline CLI remains the retained748 binary; the candidate CLI changes only this request implementation and its required types/helpers, using the same dependency pins. No core-bulk, independent-log, span-fanout or telemetry queue changes enter this comparison.

The planned full CLI matrix uses local telemetry only, normal listing/call/check/generate/export commands, distinct first-seen edit bytes, file visibility and full process exit, restoration checks, and exact output parity. Its retained volume and warm primers are explicit; it is not a cold-volume or Cloud latency experiment.

## Existing PR overlap

The retained review snapshot on 26 September lists remote cache verification #14241, module-client keying #14299, local-client source ownership #14346, and the SDK manifest work. None of their recorded scopes removes host ancestor sibling enumeration. Distributed result caching can avoid some downstream work but does not itself provide fresh local filesystem metadata. This conclusion uses the saved scopes only; it is not a fresh claim about those PRs' current heads.

The telemetry split #14303 touched `engine/opts.go` and `engine/client/filesync.go` for bounded credential-file operations. This prototype validates those existing special modes as incompatible with `ParentDirsOnly`; it does not replace or combine the credential path. A rebase should preserve that separation. Directory deletion/export changes are separate receiver/apply work, not this host import request.
